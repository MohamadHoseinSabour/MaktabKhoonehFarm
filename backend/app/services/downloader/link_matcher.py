import difflib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.episode import Episode
from app.models.enums import AssetStatus
from app.services.downloader.link_expiry import EXPIRED_LINK_ERROR_PREFIX
from app.services.downloader.link_parser import ParsedLink


@dataclass
class MatchResult:
    matched: int
    created: int
    unmatched: int
    duplicates: int
    details: list[dict]


class LinkMatcher:
    def __init__(self, db: Session) -> None:
        self.db = db

    def apply(self, course_id, links: list[ParsedLink], apply_changes: bool = True) -> MatchResult:
        episodes = self.db.query(Episode).filter(Episode.course_id == course_id).all()
        by_number = {ep.episode_number: ep for ep in episodes if ep.episode_number is not None}
        by_filename = {}
        for ep in episodes:
            for filename in [ep.video_filename, ep.subtitle_filename, ep.exercise_filename]:
                if filename:
                    by_filename[filename.lower()] = ep

        seen_urls: set[str] = set()
        matched = created = unmatched = duplicates = 0
        details: list[dict] = []

        for link in links:
            if link.url in seen_urls:
                duplicates += 1
                details.append({'url': link.url, 'result': 'duplicate'})
                continue
            seen_urls.add(link.url)

            target = self._match_episode(link, episodes, by_number, by_filename)
            if target:
                matched += 1
                details.append({'url': link.url, 'result': 'matched', 'episode_id': str(target.id)})
                if apply_changes:
                    self._apply_to_episode(target, link)
                    self._update_filename_index(by_filename, target)
                continue

            if link.episode_number is None:
                unmatched += 1
                details.append({'url': link.url, 'result': 'unmatched'})
                continue

            created += 1
            details.append({'url': link.url, 'result': 'created'})
            if apply_changes:
                new_episode = Episode(
                    course_id=course_id,
                    episode_number=link.episode_number,
                    title_en=link.episode_title,
                    hash_code=link.hash_code,
                    sort_order=link.episode_number,
                )
                self._apply_to_episode(new_episode, link)
                self.db.add(new_episode)
                episodes.append(new_episode)
                if new_episode.episode_number is not None and new_episode.episode_number not in by_number:
                    by_number[new_episode.episode_number] = new_episode
                self._update_filename_index(by_filename, new_episode)

        if apply_changes:
            self.db.commit()

        return MatchResult(
            matched=matched,
            created=created,
            unmatched=unmatched,
            duplicates=duplicates,
            details=details,
        )

    def _match_episode(self, link: ParsedLink, episodes: list[Episode], by_number: dict, by_filename: dict) -> Episode | None:
        filename_key = link.decoded_filename.lower()
        if filename_key in by_filename:
            return by_filename[filename_key]

        if link.episode_number is None:
            return None

        candidate = by_number.get(link.episode_number)
        if candidate and self._title_matches(candidate.title_en, link.episode_title):
            return candidate

        if candidate:
            return candidate

        if link.episode_title:
            scores = []
            for episode in episodes:
                if not episode.title_en:
                    continue
                ratio = difflib.SequenceMatcher(None, episode.title_en.lower(), link.episode_title.lower()).ratio()
                scores.append((ratio, episode))
            if scores:
                best_score, best_episode = max(scores, key=lambda item: item[0])
                if best_score >= 0.85:
                    return best_episode

        return None

    def _title_matches(self, episode_title: str | None, parsed_title: str | None) -> bool:
        if not episode_title or not parsed_title:
            return False
        return episode_title.strip().lower() == parsed_title.strip().lower()

    def _apply_to_episode(self, episode: Episode, link: ParsedLink) -> None:
        if link.file_type == 'video':
            episode.video_download_url = link.url
            episode.video_filename = link.decoded_filename
            if episode.video_status in {AssetStatus.ERROR, AssetStatus.DOWNLOADED}:
                episode.video_status = AssetStatus.PENDING
        elif link.file_type == 'subtitle':
            episode.subtitle_download_url = link.url
            episode.subtitle_filename = link.decoded_filename
            episode.subtitle_language = link.subtitle_language
            if episode.subtitle_status in {AssetStatus.ERROR, AssetStatus.DOWNLOADED}:
                episode.subtitle_status = AssetStatus.PENDING
        elif link.file_type == 'exercise':
            episode.exercise_download_url = link.url
            episode.exercise_filename = link.decoded_filename
            if episode.exercise_status in {AssetStatus.ERROR, AssetStatus.DOWNLOADED}:
                episode.exercise_status = AssetStatus.PENDING

        if link.hash_code:
            episode.hash_code = link.hash_code
        if link.episode_number is not None and episode.episode_number is None:
            episode.episode_number = link.episode_number
        if link.episode_title and not episode.title_en:
            episode.title_en = link.episode_title
        if episode.sort_order == 0 and link.episode_number:
            episode.sort_order = link.episode_number
        if episode.error_message and episode.error_message.startswith(EXPIRED_LINK_ERROR_PREFIX):
            episode.error_message = None

    def _update_filename_index(self, by_filename: dict, episode: Episode) -> None:
        for filename in [episode.video_filename, episode.subtitle_filename, episode.exercise_filename]:
            if filename:
                by_filename[filename.lower()] = episode
