import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.ai_config import AIConfig
from app.models.course import Course
from app.models.episode import Episode
from app.services.ai.claude_provider import ClaudeProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.prompt_manager import PromptManager
from app.services.ai.security import decrypt_secret

logger = get_logger('ai.translator')

MIN_OVERVIEW_WORDS = 220
MIN_OVERVIEW_CHARS = 1300


class AITranslator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.prompt_manager = PromptManager()
        self.cache: dict[str, str] = {}

    def translate_course(self, course: Course) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'translated': False, 'reason': 'No active AI provider configured'}

        updates = {}
        if course.title_en and not course.title_fa:
            prompt = self.prompt_manager.build_course_title_prompt(course.title_en, course.source_platform)
            updates['title_fa'] = self._call_with_cache(provider, f'title:{course.id}', prompt)

        if course.description_en and not course.description_fa:
            prompt = self.prompt_manager.build_description_prompt(course.description_en)
            updates['description_fa'] = self._call_with_cache(provider, f'desc:{course.id}', prompt)

        if updates:
            for key, value in updates.items():
                setattr(course, key, value)
            self.db.commit()

        return {'translated': bool(updates), 'updated_fields': list(updates.keys())}

    def translate_episode_titles(self, course: Course, batch_size: int = 20) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'translated': 0, 'reason': 'No active AI provider configured'}

        episodes = (
            self.db.query(Episode)
            .filter(Episode.course_id == course.id)
            .order_by(Episode.episode_number.asc().nullslast())
            .all()
        )
        pending = [ep for ep in episodes if ep.title_en and not ep.title_fa]
        translated = 0

        for i in range(0, len(pending), batch_size):
            chunk = pending[i : i + batch_size]
            prompt_payload = [{'number': ep.episode_number, 'title': ep.title_en} for ep in chunk]
            prompt = self.prompt_manager.build_episode_batch_prompt(course, prompt_payload)
            response = self._call_with_cache(provider, f'ep:{course.id}:{i}', prompt)

            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                logger.warning('Episode translation returned non-JSON payload')
                continue

            by_number = {item.get('number'): item.get('title_fa') for item in parsed if isinstance(item, dict)}
            for ep in chunk:
                if title_fa := by_number.get(ep.episode_number):
                    ep.title_fa = title_fa
                    translated += 1

        self.db.commit()
        return {'translated': translated, 'total_pending': len(pending)}

    def translate_episode_title(self, course: Course, episode: Episode) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'translated': False, 'reason': 'No active AI provider configured'}
        if not episode.title_en:
            return {'translated': False, 'reason': 'Episode does not have English title'}

        prompt = self.prompt_manager.build_single_episode_title_prompt(course, episode.episode_number, episode.title_en)
        translated_title = self._call_with_cache(provider, f'ep-single:{episode.id}', prompt).strip()
        if not translated_title:
            return {'translated': False, 'reason': 'Provider returned empty translation'}

        episode.title_fa = translated_title
        self.db.commit()
        return {'translated': True, 'title_fa': translated_title}

    def generate_course_content(self, course: Course, episodes: list[Episode]) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'generated': False, 'reason': 'No active AI provider configured'}

        payload = self._build_course_context(course, episodes)
        base_prompt = self.prompt_manager.build_course_content_prompt(json.dumps(payload, ensure_ascii=False, indent=2))

        last_reason = 'AI content generation failed'
        for attempt in range(5):
            extra_rules = ''
            if attempt > 0:
                extra_rules = (
                    '\n\nIMPORTANT RETRY REQUIREMENT:\n'
                    'The previous output was not acceptable. '
                    'Make `course_overview` significantly longer and more comprehensive '
                    f'(minimum {MIN_OVERVIEW_WORDS} words and minimum {MIN_OVERVIEW_CHARS} characters).'
                )

            raw = provider.translate(f'{base_prompt}{extra_rules}')
            parsed = self._parse_json_object(raw)
            if not parsed:
                last_reason = 'AI response is not valid JSON object'
                continue

            normalized = self._normalize_course_content(parsed)
            if not normalized:
                last_reason = 'AI response missing required fields'
                continue

            overview = normalized['course_overview']
            if not self._is_comprehensive_overview(overview):
                expanded = self._expand_course_overview(provider, payload, overview)
                if expanded and self._is_comprehensive_overview(expanded):
                    normalized['course_overview'] = expanded
                else:
                    last_reason = 'Generated course overview is too short'
                    continue

            metadata = dict(course.extra_metadata or {})
            metadata['ai_course_content'] = normalized
            course.extra_metadata = metadata
            self.db.commit()
            return {'generated': True, 'content': normalized}

        return {'generated': False, 'reason': last_reason}

    def _call_with_cache(self, provider, cache_key: str, prompt: str) -> str:
        if cache_key in self.cache:
            return self.cache[cache_key]
        result = provider.translate(prompt)
        self.cache[cache_key] = result
        return result

    def _get_provider(self):
        configs = (
            self.db.query(AIConfig)
            .filter(AIConfig.is_active.is_(True))
            .order_by(AIConfig.priority.asc())
            .all()
        )

        for cfg in configs:
            try:
                api_key = decrypt_secret(cfg.api_key)
                provider_name = cfg.provider.lower()
                if provider_name == 'openai':
                    return OpenAIProvider(api_key=api_key, model=cfg.model_name, endpoint_url=cfg.endpoint_url)
                if provider_name == 'claude':
                    return ClaudeProvider(api_key=api_key, model=cfg.model_name, endpoint_url=cfg.endpoint_url)
            except Exception as exc:
                logger.warning('Failed to initialize provider %s: %s', cfg.provider, exc)
                continue
        return None

    def _build_course_context(self, course: Course, episodes: list[Episode]) -> dict[str, Any]:
        episode_titles = [
            ep.title_en
            for ep in sorted(episodes, key=lambda item: (item.episode_number is None, item.episode_number or 0))[:15]
            if ep.title_en
        ]
        return {
            'title_en': course.title_en,
            'title_fa': course.title_fa,
            'description_en': course.description_en,
            'description_fa': course.description_fa,
            'instructor': course.instructor,
            'category': course.category,
            'tags': course.tags or [],
            'level': course.level,
            'duration': course.duration,
            'lectures_count': course.lectures_count,
            'language': course.language,
            'source_platform': course.source_platform,
            'episode_titles_sample': episode_titles,
        }

    def _parse_json_object(self, raw: str) -> dict[str, Any] | None:
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

        start = raw.find('{')
        end = raw.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    def _normalize_course_content(self, data: dict[str, Any]) -> dict[str, Any] | None:
        course_overview = self._normalize_text(data.get('course_overview'))
        prerequisites = self._normalize_list(data.get('prerequisites'))
        prerequisites_description = self._normalize_text(data.get('prerequisites_description'))
        what_you_will_learn = self._normalize_list(data.get('what_you_will_learn'))
        course_goals = self._normalize_list(data.get('course_goals'))

        if not all([course_overview, prerequisites, prerequisites_description, what_you_will_learn, course_goals]):
            return None

        return {
            'course_overview': course_overview,
            'prerequisites': prerequisites,
            'prerequisites_description': prerequisites_description,
            'what_you_will_learn': what_you_will_learn,
            'course_goals': course_goals,
        }

    def _normalize_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        output = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    output.append(text)
        return output

    def _is_comprehensive_overview(self, text: str) -> bool:
        words = len([part for part in text.split() if part.strip()])
        chars = len(text)
        return words >= MIN_OVERVIEW_WORDS and chars >= MIN_OVERVIEW_CHARS

    def _expand_course_overview(self, provider, course_payload: dict[str, Any], short_overview: str) -> str | None:
        prompt = (
            'You are improving a Persian course page description.\n'
            f'Target: produce a comprehensive long-form overview with at least {MIN_OVERVIEW_WORDS} words '
            f'and at least {MIN_OVERVIEW_CHARS} characters.\n'
            'Use only the provided data and keep claims realistic.\n'
            'Return plain Persian text only (not JSON, no markdown, no list markers).\n\n'
            f'Course data:\n{json.dumps(course_payload, ensure_ascii=False, indent=2)}\n\n'
            f'Current short overview:\n{short_overview}\n\n'
            'Expanded overview:'
        )
        try:
            result = provider.translate(prompt).strip()
            return result or None
        except Exception:
            return None
