import json
import html
from dataclasses import dataclass
from difflib import SequenceMatcher
import mimetypes
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.episode import Episode
from app.models.setting import Setting
from app.services.processor.video_metadata import extract_video_metadata, probe_duration_seconds, remux_mp4_for_upload


class UploadAutomationError(Exception):
    pass


class UploadConfigurationError(UploadAutomationError):
    pass


class UploadAuthExpiredError(UploadAutomationError):
    pass


@dataclass
class UploadAutomationConfig:
    headless: bool
    target_url: str
    cookies_json: str
    search_input_selector: str
    course_result_xpath_template: str
    sections_button_xpath: str
    units_button_xpath: str
    login_check_selector: str
    episode_page_indicator_selector: str
    geckodriver_path: str | None


@dataclass
class MirzaCourseRoute:
    url: str
    created: bool
    source: str
    course_id: str | None = None


@dataclass
class MarketplaceChapter:
    id: str
    title: str
    units_url: str
    edit_url: str | None = None


@dataclass
class MarketplaceUnit:
    id: str
    title: str
    edit_url: str


class MirzaApiClient:
    REQUEST_TIMEOUT_SECONDS = 180
    REQUEST_ATTEMPTS = 3
    DEFAULT_TOPIC_TITLE = 'ChatGPT'

    def __init__(self, config: UploadAutomationConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.target_parts = urlsplit(config.target_url)
        self.target_host = (self.target_parts.hostname or '').strip()
        self.target_base = f'{self.target_parts.scheme or "https"}://{self.target_host}'
        self.mooc_base = 'https://maktabkhooneh.org'
        self.token: str | None = None
        self._load_cookies(config.cookies_json)

    def validate_session(self) -> dict[str, Any]:
        data = self._request_json('GET', '/courses/teacher-courses/', params={'page': 1})
        return {
            'valid': True,
            'message': 'Upload API session is valid.',
            'courses_count': self._payload_count(data),
        }

    def resolve_course_route(self, course: Course, title_matches: Any) -> MirzaCourseRoute:
        query = (course.title_fa or course.title_en or course.slug or '').strip()
        if not query:
            raise UploadConfigurationError('Course title is empty and cannot be used for search.')

        existing = self._find_teacher_course(query, title_matches)
        if existing:
            course_id = self._extract_course_id(existing)
            chapters_url = self._extract_course_url(existing, course_id, 'chapters')
            if chapters_url:
                return MirzaCourseRoute(url=chapters_url, created=False, source='teacher-courses-api', course_id=course_id)

        draft = self._create_draft(course)
        redirect_url = str(draft.get('redirect_url') or draft.get('url') or '').strip()
        if not redirect_url:
            raise UploadConfigurationError('Course draft API did not return redirect_url.')
        return MirzaCourseRoute(
            url=urljoin(self.config.target_url, redirect_url),
            created=True,
            source='draft-api',
            course_id=self._extract_course_id(draft),
        )

    def _load_cookies(self, raw: str) -> None:
        try:
            cookies = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UploadConfigurationError('Cookies JSON is invalid.') from exc
        if not isinstance(cookies, list):
            raise UploadConfigurationError('Cookies JSON must be a list.')

        has_target_cookie = False
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get('name') or '').strip()
            value = cookie.get('value')
            if not name or value is None:
                continue
            domain = str(cookie.get('domain') or '').strip().lstrip('.')
            path = str(cookie.get('path') or '/')
            if domain and self._domain_matches(self.target_host, domain):
                has_target_cookie = True
            if name == 'token':
                self.token = str(value)
            cookie_kwargs: dict[str, str] = {'path': path}
            if domain:
                cookie_kwargs['domain'] = domain
            self.session.cookies.set(name, str(value), **cookie_kwargs)

        if not has_target_cookie:
            raise UploadConfigurationError(
                f'No cookie domain matches target host "{self.target_host}". '
                'Export cookies while logged in on maktabkhooneh/mirza and save them in upload_cookies_json.'
            )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        base_url: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        base = (base_url or f'{self.target_base}/api/v1').rstrip('/')
        url = f'{base}/{endpoint.lstrip("/")}'
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        response = None
        last_error: requests.RequestException | None = None
        for attempt in range(1, self.REQUEST_ATTEMPTS + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.REQUEST_ATTEMPTS:
                    time.sleep(min(5 * attempt, 15))

        if response is None:
            raise UploadConfigurationError(f'Mirza API request failed after retries: {last_error}') from last_error
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get('Location', '')
            if self._is_login_location(location):
                raise UploadAuthExpiredError(self._auth_error(location))
        if response.status_code in {401, 403}:
            raise UploadAuthExpiredError(self._auth_error(url))
        if response.status_code >= 400:
            raise UploadConfigurationError(
                f'Mirza API request failed: {response.status_code} {response.text[:300]}'
            )
        try:
            return response.json()
        except ValueError as exc:
            raise UploadConfigurationError(f'Mirza API did not return JSON. url={url}') from exc

    def _find_teacher_course(self, query: str, title_matches: Any) -> dict[str, Any] | None:
        normalized_query = self._normalize_title_text(query)
        seen_ids: set[str] = set()
        for params in ({'search': query, 'page': 1}, {'page': 1}):
            data = self._request_json('GET', '/courses/teacher-courses/', params=params)
            for item in self._iter_items(data):
                item_id = str(item.get('id') or item.get('course_id') or item.get('pk') or '')
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                for title in self._title_candidates(item):
                    if title_matches(self._normalize_title_text(title), normalized_query):
                        return item
        return None

    def _create_draft(self, course: Course) -> dict[str, Any]:
        title = self._course_draft_title(course)
        topic_id = self._select_topic_id(title)
        payload = {'title': title, 'main_topic': topic_id}
        data = self._request_json('POST', '/courses/draft/', json_body=payload)
        if not isinstance(data, dict):
            raise UploadConfigurationError('Course draft API returned an unexpected payload.')
        return data

    def _select_topic_id(self, query: str) -> int:
        preferred_topic = self._find_topic_id(self.DEFAULT_TOPIC_TITLE, exact_title=self.DEFAULT_TOPIC_TITLE)
        if preferred_topic is not None:
            return preferred_topic

        preferred_topic = self._find_topic_id(self.DEFAULT_TOPIC_TITLE)
        if preferred_topic is not None:
            return preferred_topic

        data = self._request_json(
            'GET',
            '/courses/topics/',
            base_url=f'{self.mooc_base}/api/v1',
            params={'page': 1, 'search': query},
        )
        items = list(self._iter_items(data))
        if not items:
            data = self._request_json('GET', '/courses/topics/', base_url=f'{self.mooc_base}/api/v1', params={'page': 1})
            items = list(self._iter_items(data))
        for item in items:
            raw_id = item.get('id')
            if raw_id is not None:
                return int(raw_id)
        raise UploadConfigurationError('Could not resolve a main_topic from Maktab topics API.')

    def _find_topic_id(self, query: str, *, exact_title: str | None = None) -> int | None:
        data = self._request_json(
            'GET',
            '/courses/topics/',
            base_url=f'{self.mooc_base}/api/v1',
            params={'page': 1, 'search': query},
        )
        items = list(self._iter_items(data))
        if exact_title:
            normalized = self._normalize_title_text(exact_title)
            for item in items:
                title = self._normalize_title_text(str(item.get('title') or item.get('name') or ''))
                if title == normalized and item.get('id') is not None:
                    return int(item['id'])
        for item in items:
            if item.get('id') is not None:
                return int(item['id'])
        return None

    def _course_draft_title(self, course: Course) -> str:
        title_fa = (course.title_fa or '').strip()
        title_en = (course.title_en or '').strip()
        if title_fa and title_en and self._normalize_title_text(title_fa) != self._normalize_title_text(title_en):
            return f'{title_fa} ({title_en})'
        return (title_fa or title_en or course.slug or '').strip()

    def _extract_course_url(self, item: dict[str, Any], course_id: str | None, section: str) -> str | None:
        for key in ('chapters_url', 'chapter_url', 'url', 'absolute_url', 'redirect_url', 'edit_url'):
            raw = str(item.get(key) or '').strip()
            if raw and f'/{section}/' in raw:
                return urljoin(self.config.target_url, raw)
        if course_id:
            return urljoin(self.config.target_url, f'/courses/{course_id}/{section}/')
        return None

    def _extract_course_id(self, item: dict[str, Any]) -> str | None:
        for key in ('id', 'course_id', 'pk'):
            value = item.get(key)
            if value is not None:
                return str(value)
        for key in ('redirect_url', 'url', 'absolute_url', 'edit_url'):
            match = re.search(r'/courses/([^/]+)/', str(item.get(key) or ''))
            if match:
                return match.group(1)
        return None

    def _iter_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ('results', 'data', 'items', 'courses'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    def _payload_count(self, payload: Any) -> int | None:
        if isinstance(payload, dict) and isinstance(payload.get('count'), int):
            return payload['count']
        items = self._iter_items(payload)
        return len(items) if items else None

    def _title_candidates(self, item: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ('title', 'name', 'title_fa', 'title_en', 'course_title'):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        return values

    def _normalize_title_text(self, value: str) -> str:
        normalized = (value or '').strip().lower()
        normalized = normalized.replace('ي', 'ی').replace('ك', 'ک')
        normalized = re.sub(r'[\u200c\u200f\u202a-\u202e]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s\u0600-\u06FF\-\(\)]', '', normalized)
        return normalized.strip()

    def _domain_matches(self, host: str, domain: str) -> bool:
        clean_host = (host or '').strip().lower().lstrip('.')
        clean_domain = (domain or '').strip().lower().lstrip('.')
        return bool(clean_host and clean_domain) and (
            clean_host == clean_domain
            or clean_host.endswith(f'.{clean_domain}')
            or clean_domain.endswith(f'.{clean_host}')
        )

    def _is_login_location(self, location: str) -> bool:
        lowered = (location or '').lower()
        return any(token in lowered for token in ('login', 'signin', 'auth'))

    def _auth_error(self, current_url: str) -> str:
        return f'Mirza API auth failed. Update upload_cookies_json/token from a logged-in mirza session. url={current_url}'


class MaktabMarketplaceClient:
    CHAPTER_TITLE = 'ویدیو های دوره'
    REQUEST_TIMEOUT_SECONDS = 180

    def __init__(self, config: UploadAutomationConfig) -> None:
        self.config = config
        self.base_url = 'https://maktabkhooneh.org'
        self.session = requests.Session()
        self.token: str | None = None
        self._load_cookies(config.cookies_json)

    def upload_course_episodes(
        self,
        course: Course,
        episodes: list[Episode],
        route: MirzaCourseRoute,
    ) -> dict[str, Any]:
        course_id = route.course_id
        if not course_id:
            raise UploadConfigurationError('Could not resolve Maktab course id for marketplace upload.')

        detail_result = self.ensure_course_details(course_id, course, episodes)
        chapter = self.ensure_video_chapter(course_id)
        results = [
            self.upload_episode(course_id, chapter, episode)
            for episode in sorted(episodes, key=lambda item: (item.episode_number or 0, item.sort_order or 0))
        ]
        order_sync_result = {'result': 'synced'}
        try:
            self._sync_unit_order(chapter, list(course.episodes or []))
        except Exception as exc:
            order_sync_result = {'result': 'warning', 'error': str(exc)}
        return {
            'ok': True,
            'query': (course.title_fa or course.title_en or course.slug or '').strip(),
            'headless': False,
            'current_url': self._absolute(chapter.units_url),
            'browser_kept_open': False,
            'results': results,
            'processed_count': len(results),
            'units_list_url': self._absolute(chapter.units_url),
            'used_cached_units_url': False,
            'api_route_source': route.source,
            'upload_transport': 'maktab-marketplace-api',
            'chapter_id': chapter.id,
            'chapter_title': chapter.title,
            'course_detail_result': detail_result,
            'order_sync': order_sync_result,
        }

    def ensure_course_details(self, course_id: str, course: Course, episodes: list[Episode]) -> dict[str, Any]:
        detail_path = f'/marketplace/teacher/course/{course_id}/detail/edit'
        soup = self._get_soup(detail_path)
        csrf = self._csrf_from_soup(soup)
        fields = self._course_detail_form_fields(soup, csrf, course)
        thumbnail_path = self._course_thumbnail_file_path(course)
        file_handles: list[Any] = []
        try:
            if thumbnail_path:
                handle = open(thumbnail_path, 'rb')
                file_handles.append(handle)
                fields.append(
                    (
                        'image',
                        (
                            Path(thumbnail_path).name,
                            handle,
                            mimetypes.guess_type(thumbnail_path)[0] or 'image/jpeg',
                        ),
                    )
                )
            response = self._post_form(detail_path, {}, files=fields)
            self._assert_course_detail_saved(response, detail_path)
        finally:
            for handle in file_handles:
                handle.close()

        teaser_result: dict[str, Any]
        try:
            teaser_result = self._upload_first_episode_as_teaser(course_id, episodes)
        except Exception as exc:
            teaser_result = {
                'result': 'warning',
                'error': str(exc),
            }
        return {
            'detail_url': self._absolute(detail_path),
            'form_status_code': response.status_code,
            'thumbnail_uploaded': bool(thumbnail_path),
            'thumbnail_path': thumbnail_path,
            'description_updated': True,
            'prerequisites_updated': True,
            'price': '99000',
            'teaser': teaser_result,
        }

    def ensure_video_chapter(self, course_id: str) -> MarketplaceChapter:
        chapters = self._list_chapters(course_id)
        normalized_target = self._normalize_title_text(self.CHAPTER_TITLE)
        for chapter in chapters:
            if self._normalize_title_text(chapter.title) == normalized_target:
                return chapter

        if len(chapters) == 1 and chapters[0].edit_url:
            return self._rename_chapter(course_id, chapters[0], self.CHAPTER_TITLE)

        return self._create_chapter(course_id, self.CHAPTER_TITLE)

    def upload_episode(self, course_id: str, chapter: MarketplaceChapter, episode: Episode) -> dict[str, Any]:
        outcome: dict[str, Any] = {
            'episode_id': str(episode.id),
            'episode_number': episode.episode_number,
            'episode_title': (episode.title_fa or episode.title_en or '').strip(),
            'result': 'error',
            'unit_action': None,
            'error': None,
            'form_filled': False,
            'form_title': None,
            'subtitle_attached': False,
            'subtitle_path': None,
            'subtitle_missing_reason': None,
            'video_file': None,
            'video_probe': None,
            'video_probe_source': None,
            'video_normalized_for_upload': False,
            'progress': None,
            'returned_to_units': True,
            'units_list_url': self._absolute(chapter.units_url),
            'current_url': self._absolute(chapter.units_url),
        }

        video_file = self._episode_video_file_path(episode)
        outcome['video_file'] = video_file
        if not video_file:
            outcome['result'] = 'skipped_missing_video'
            outcome['error'] = 'Video file was not found for this episode.'
            return outcome

        unit = self._find_unit(chapter, episode)
        if unit is None:
            unit = self._create_lecture_unit(course_id, chapter, episode)
            outcome['unit_action'] = 'create_new'
            outcome['form_filled'] = True
            outcome['form_title'] = self._episode_form_title(episode)
            subtitle_path = self._episode_subtitle_vtt_path(episode)
            outcome['subtitle_path'] = subtitle_path
            outcome['subtitle_attached'] = bool(subtitle_path)
            outcome['subtitle_missing_reason'] = None if subtitle_path else 'processed_vtt_not_found'
        else:
            outcome['unit_action'] = 'update_existing'
            outcome['matched_title'] = unit.title

        upload_info = self._upload_video_to_unit(unit, video_file)
        outcome['video_probe'] = upload_info.get('probe')
        outcome['video_probe_source'] = upload_info.get('source_probe')
        outcome['video_normalized_for_upload'] = bool(upload_info.get('normalized'))
        outcome['result'] = 'uploaded'
        outcome['progress'] = '100%'
        outcome['editor_url'] = self._absolute(unit.edit_url)
        outcome['current_url'] = self._absolute(chapter.units_url)
        return outcome

    def _course_detail_form_fields(self, soup: BeautifulSoup, csrf: str, course: Course) -> list[tuple[str, Any]]:
        goal_count = max(len(soup.select("input[name='learning_goals']")), 4)
        fields = self._extract_form_fields(soup)
        override_names = {
            'csrfmiddlewaretoken',
            'description',
            'prerequisite_description',
            'content_price',
            'learning_goals',
            'english_title',
        }
        fields = [field for field in fields if field[0] not in override_names]
        fields.insert(0, ('csrfmiddlewaretoken', (None, csrf)))

        english_title = (
            self._clean_text(getattr(course, 'title_en', None))
            or self._clean_text(getattr(course, 'slug', None))
            or self._clean_text(getattr(course, 'title_fa', None))
            or 'Course'
        )
        fields.extend(
            [
                ('english_title', (None, english_title)),
                ('description', (None, self._course_description_html(course))),
                ('prerequisite_description', (None, self._course_prerequisites_html(course))),
                ('content_price', (None, '99000')),
            ]
        )

        for goal in self._course_learning_goals(course, goal_count):
            fields.append(('learning_goals', (None, goal)))
        return fields

    def _extract_form_fields(self, soup: BeautifulSoup) -> list[tuple[str, Any]]:
        target_form = None
        for form in soup.find_all('form'):
            if form.select_one("[name='description'], [name='english_title'], [name='learning_goals']"):
                target_form = form
                break
        if target_form is None:
            target_form = soup.find('form')
        if target_form is None:
            return []

        fields: list[tuple[str, Any]] = []

        for input_node in target_form.select('input[name]'):
            if input_node.has_attr('disabled'):
                continue
            name = str(input_node.get('name') or '').strip()
            if not name:
                continue
            input_type = str(input_node.get('type') or 'text').strip().lower()
            if input_type in {'file', 'submit', 'button', 'reset', 'image'}:
                continue
            if input_type in {'checkbox', 'radio'} and not input_node.has_attr('checked'):
                continue
            value = str(input_node.get('value') or '')
            if input_type in {'checkbox', 'radio'} and not value:
                value = 'on'
            fields.append((name, (None, value)))

        for textarea in target_form.select('textarea[name]'):
            if textarea.has_attr('disabled'):
                continue
            name = str(textarea.get('name') or '').strip()
            if not name:
                continue
            fields.append((name, (None, textarea.get_text() or '')))

        for select in target_form.select('select[name]'):
            if select.has_attr('disabled'):
                continue
            name = str(select.get('name') or '').strip()
            if not name:
                continue
            options = select.select('option[selected]')
            if not options and not select.has_attr('multiple'):
                first_option = select.find('option')
                options = [first_option] if first_option is not None else []
            for option in options:
                value = str(option.get('value') or '').strip()
                if value:
                    fields.append((name, (None, value)))

        return fields

    def _course_ai_content(self, course: Course) -> dict[str, Any]:
        metadata: Any = course.extra_metadata or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if not isinstance(metadata, dict):
            return {}
        content = metadata.get('ai_course_content')
        return content if isinstance(content, dict) else {}

    def _course_description_html(self, course: Course) -> str:
        content = self._course_ai_content(course)
        description = (
            self._clean_text(content.get('course_overview'))
            or self._clean_text(getattr(course, 'description_fa', None))
            or self._clean_text(getattr(course, 'description_en', None))
            or 'توضیحات دوره به زودی تکمیل می‌شود.'
        )
        return self._paragraphs_to_html(description)

    def _course_prerequisites_html(self, course: Course) -> str:
        content = self._course_ai_content(course)
        prerequisites = self._clean_text_list(content.get('prerequisites'))
        prerequisite_description = self._clean_text(content.get('prerequisites_description'))
        if not prerequisite_description and prerequisites:
            prerequisite_description = 'برای استفاده بهتر از این دوره، آشنایی اولیه با موارد زیر پیشنهاد می‌شود.'
        if not prerequisite_description:
            prerequisite_description = 'آشنایی مقدماتی با ChatGPT و مفاهیم پایه هوش مصنوعی برای شروع این دوره کافی است.'

        lines = [prerequisite_description]
        if prerequisites:
            lines.append('پیش‌نیازهای پیشنهادی:')
            lines.extend(f'- {item}' for item in prerequisites)
        return self._paragraphs_to_html('\n'.join(lines))

    def _course_learning_goals(self, course: Course, count: int) -> list[str]:
        content = self._course_ai_content(course)
        candidates = self._clean_text_list(content.get('what_you_will_learn'))
        candidates.extend(self._clean_text_list(content.get('course_goals')))
        candidates.extend(self._course_description_learning_goals(course))
        fallback = [
            'کاربردهای عملی ChatGPT در حل مسئله',
            'طراحی پرامپت‌های دقیق و قابل استفاده',
            'تحقیق و برنامه‌ریزی با ابزارهای هوش مصنوعی',
            'تمرین عملی برای تبدیل مفاهیم به مهارت',
        ]

        goals: list[str] = []
        seen: set[str] = set()
        for item in candidates + fallback:
            item = item[:255].strip()
            normalized = self._normalize_title_text(item)
            if normalized and normalized not in seen:
                goals.append(item)
                seen.add(normalized)
            if len(goals) >= count:
                break
        return goals

    def _course_description_learning_goals(self, course: Course) -> list[str]:
        text = ' '.join(
            item
            for item in (
                self._clean_text(getattr(course, 'title_fa', None)),
                self._clean_text(getattr(course, 'title_en', None)),
                self._clean_text(getattr(course, 'description_fa', None)),
                self._clean_text(getattr(course, 'description_en', None)),
            )
            if item
        )
        normalized = self._normalize_title_text(text)
        goals: list[str] = []

        keyword_goals = [
            (('chatgpt', 'چتgpt', 'چت جی پی تی', 'چت‌جی‌پی‌تی'), 'کاربردهای عملی ChatGPT در انجام کارهای تخصصی'),
            (('پرامپت', 'prompt'), 'طراحی پرامپت‌های دقیق برای پاسخ‌های قابل استفاده'),
            (('ایجنت', 'agent'), 'کار با ایجنت‌های هوش مصنوعی برای اجرای تسک‌ها'),
            (('تحقیق', 'جستجو', 'جست‌وجو', 'research', 'search'), 'تحقیق و جست‌وجوی عمیق با ابزارهای هوش مصنوعی'),
            (('برنامه ریزی', 'برنامه‌ریزی', 'planning'), 'برنامه‌ریزی ساختاریافته با کمک هوش مصنوعی'),
            (('اتوماسیون', 'automation'), 'اتوماسیون فرایندهای تکراری با ابزارهای هوش مصنوعی'),
            (('مرورگر', 'browser'), 'به‌کارگیری ایجنت‌های مبتنی بر مرورگر'),
            (('پروژه', 'project'), 'ساخت پروژه‌های سفارشی با رویکرد عملی'),
            (('زمینه', 'context'), 'استفاده از زمینه برای بهبود کیفیت پاسخ‌ها'),
        ]
        for keywords, goal in keyword_goals:
            if any(self._normalize_title_text(keyword) in normalized for keyword in keywords):
                goals.append(goal)

        if text and len(goals) < 4:
            goals.extend(
                [
                    'درک مفاهیم اصلی مطرح‌شده در دوره',
                    'به‌کارگیری آموخته‌ها در سناریوهای واقعی',
                    'تحلیل نمونه‌های عملی مرتبط با موضوع دوره',
                    'تبدیل توضیحات دوره به مهارت‌های قابل اجرا',
                ]
            )
        return goals

    def _clean_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = re.sub(r'\s+', ' ', value).strip()
        return text or None

    def _clean_text_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = self._clean_text(item)
            if text:
                items.append(text)
        return items

    def _paragraphs_to_html(self, value: str) -> str:
        if '<p' in value.lower() or '<br' in value.lower():
            return value
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if not lines:
            lines = [value.strip()]
        return '\n'.join(f'<p>{html.escape(line)}</p>' for line in lines if line)

    def _course_thumbnail_file_path(self, course: Course) -> str | None:
        candidates = [
            (getattr(course, 'thumbnail_local', '') or '').strip(),
            (getattr(course, 'cover_local_path', '') or '').strip(),
        ]
        for raw in candidates:
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.is_file():
                return str(candidate.resolve())
        return None

    def _upload_first_episode_as_teaser(
        self,
        course_id: str,
        episodes: list[Episode],
    ) -> dict[str, Any]:
        ordered = sorted(episodes, key=lambda item: (item.episode_number or 0, item.sort_order or 0))
        first_episode = next((episode for episode in ordered if self._episode_video_file_path(episode)), None)
        if first_episode is None:
            return {'result': 'skipped_missing_video', 'episode_number': None, 'video_file': None}

        video_path = self._episode_video_file_path(first_episode)
        if not video_path:
            return {
                'result': 'skipped_missing_video',
                'episode_number': first_episode.episode_number,
                'video_file': None,
            }

        detail_path = f'/marketplace/teacher/course/{course_id}/detail/edit'
        detail_url = self._absolute(detail_path)
        soup = self._get_soup(detail_path)
        csrf = self._csrf_from_soup(soup)
        upload_type = self._script_value(soup, 'type') or 'course'
        obj_id = self._script_value(soup, 'objId') or course_id
        source = self._script_value(soup, 'user_type') or 'teacher'
        is_teaser = self._script_bool_value(soup, 'is_teaser', default=True)
        self._upload_direct_video(
            referer_url=detail_url,
            video_path=video_path,
            upload_type=upload_type,
            obj_id=obj_id,
            csrf=csrf,
            source=source,
            is_teaser=is_teaser,
        )
        return {
            'result': 'uploaded',
            'episode_number': first_episode.episode_number,
            'video_file': video_path,
            'type': upload_type,
            'id': obj_id,
            'is_teaser': is_teaser,
        }

    def _load_cookies(self, raw: str) -> None:
        try:
            cookies = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UploadConfigurationError('Cookies JSON is invalid.') from exc
        if not isinstance(cookies, list):
            raise UploadConfigurationError('Cookies JSON must be a list.')

        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get('name') or '').strip()
            value = cookie.get('value')
            if not name or value is None:
                continue
            if name == 'token':
                self.token = str(value)
            cookie_kwargs: dict[str, str] = {'path': str(cookie.get('path') or '/')}
            domain = str(cookie.get('domain') or '').strip().lstrip('.')
            if domain:
                cookie_kwargs['domain'] = domain
            self.session.cookies.set(name, str(value), **cookie_kwargs)

        if not self.token:
            raise UploadConfigurationError('upload_cookies_json does not include token cookie.')

    def _headers(self, *, accept: str = 'text/html', referer: str | None = None) -> dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self.token}',
            'User-Agent': 'Mozilla/5.0',
            'Accept': accept,
        }
        if referer:
            headers['Referer'] = referer
            headers['Origin'] = self.base_url
        return headers

    def _get_soup(self, url_or_path: str) -> BeautifulSoup:
        url = self._absolute(url_or_path)
        response = self.session.get(
            url,
            headers=self._headers(accept='text/html'),
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        self._raise_for_response(response, url)
        return BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')

    def _post_form(
        self,
        url_or_path: str,
        data: dict[str, Any],
        files: Any = None,
    ) -> requests.Response:
        url = self._absolute(url_or_path)
        response = self.session.post(
            url,
            headers=self._headers(accept='text/html,application/json', referer=url),
            data=data,
            files=files,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        self._raise_for_response(response, url, allow_redirect=True)
        return response

    def _post_multipart_fields(self, url_or_path: str, fields: dict[str, Any]) -> requests.Response:
        multipart_fields = {key: (None, str(value)) for key, value in fields.items()}
        return self._post_form(url_or_path, {}, files=multipart_fields)

    def _assert_course_detail_saved(self, response: requests.Response, url_or_path: str) -> None:
        if response.status_code in {301, 302, 303, 307, 308}:
            return
        content_type = str(response.headers.get('Content-Type') or '').lower()
        if 'html' not in content_type and response.content:
            return

        soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
        errors: list[str] = []
        for item in soup.select('.errorlist li, .invalid-feedback, .help-block.error, .form-error'):
            text = item.get_text(' ', strip=True)
            if text:
                errors.append(text)
        if errors:
            message = '; '.join(dict.fromkeys(errors))
            raise UploadConfigurationError(
                f'Course detail form validation failed at {self._absolute(url_or_path)}: {message}'
            )

    def _raise_for_response(self, response: requests.Response, url: str, *, allow_redirect: bool = False) -> None:
        if allow_redirect and response.status_code in {301, 302, 303, 307, 308}:
            return
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get('Location', '')
            if any(token in location.lower() for token in ('login', 'signin', 'auth')):
                raise UploadAuthExpiredError(f'Maktab auth failed. Update cookies/token. url={location}')
        if response.status_code in {401, 403}:
            raise UploadAuthExpiredError(f'Maktab auth failed. Update cookies/token. url={url}')
        if response.status_code >= 400:
            raise UploadConfigurationError(
                f'Maktab marketplace request failed: {response.status_code} {response.text[:300]}'
            )

    def _list_chapters(self, course_id: str) -> list[MarketplaceChapter]:
        soup = self._get_soup(f'/marketplace/teacher/course/{course_id}/chapters/')
        chapters: list[MarketplaceChapter] = []
        for units_link in soup.select("a[href*='/chapters/'][href*='/units/']"):
            units_url = units_link.get('href') or ''
            match = re.search(r'/chapters/(\d+)/units/', units_url)
            if not match:
                continue
            chapter_id = match.group(1)
            row = units_link.find_parent('li', class_='item') or units_link.find_parent('div', class_='col-12')
            title = ''
            edit_url = None
            if row:
                title_cell = row.select_one('.col-4')
                if title_cell:
                    title = title_cell.get_text(' ', strip=True)
                edit = row.select_one("a[href*='/chapters/edit/?chapter_id=']")
                if edit:
                    edit_url = edit.get('href')
            chapters.append(MarketplaceChapter(id=chapter_id, title=title, units_url=units_url, edit_url=edit_url))
        return chapters

    def _create_chapter(self, course_id: str, title: str) -> MarketplaceChapter:
        edit_path = f'/marketplace/teacher/course/{course_id}/chapters/edit/'
        soup = self._get_soup(edit_path)
        csrf = self._csrf_from_soup(soup)
        response = self._post_multipart_fields(edit_path, {'csrfmiddlewaretoken': csrf, 'title': title})
        location = response.headers.get('Location') or ''
        match = re.search(r'/chapters/(\d+)/units/', location)
        if match:
            return MarketplaceChapter(
                id=match.group(1),
                title=title,
                units_url=location,
                edit_url=f'/marketplace/teacher/course/{course_id}/chapters/edit/?chapter_id={match.group(1)}',
            )
        return self.ensure_video_chapter(course_id)

    def _rename_chapter(self, course_id: str, chapter: MarketplaceChapter, title: str) -> MarketplaceChapter:
        edit_url = chapter.edit_url or f'/marketplace/teacher/course/{course_id}/chapters/edit/?chapter_id={chapter.id}'
        soup = self._get_soup(edit_url)
        csrf = self._csrf_from_soup(soup)
        self._post_multipart_fields(edit_url, {'csrfmiddlewaretoken': csrf, 'title': title})
        return MarketplaceChapter(id=chapter.id, title=title, units_url=chapter.units_url, edit_url=edit_url)

    def _find_unit(self, chapter: MarketplaceChapter, episode: Episode) -> MarketplaceUnit | None:
        soup = self._get_soup(chapter.units_url)
        candidates = [self._normalize_title_text(item) for item in self._episode_title_candidates(episode)]
        candidates = [item for item in candidates if item]
        for edit_link in soup.select("a[href*='/units/edit/?unit_id=']"):
            href = edit_link.get('href') or ''
            match = re.search(r'unit_id=(\d+)', href)
            if not match:
                continue
            row = edit_link.find_parent('li', class_='item') or edit_link.find_parent('div', class_='col-12')
            raw_title = ''
            if row:
                title_cell = row.select_one('.col-4')
                if title_cell:
                    raw_title = title_cell.get_text(' ', strip=True)
            row_title = self._normalize_title_text(raw_title)
            if row_title and any(self._titles_match(row_title, candidate) for candidate in candidates):
                return MarketplaceUnit(id=match.group(1), title=raw_title, edit_url=href)
        return None

    def _list_units(self, chapter: MarketplaceChapter) -> list[MarketplaceUnit]:
        soup = self._get_soup(chapter.units_url)
        units: list[MarketplaceUnit] = []
        for edit_link in soup.select("a[href*='/units/edit/?unit_id=']"):
            href = edit_link.get('href') or ''
            match = re.search(r'unit_id=(\d+)', href)
            if not match:
                continue
            row = edit_link.find_parent('li', class_='item') or edit_link.find_parent('div', class_='col-12')
            raw_title = ''
            if row:
                title_cell = row.select_one('.col-4')
                if title_cell:
                    raw_title = title_cell.get_text(' ', strip=True)
            units.append(MarketplaceUnit(id=match.group(1), title=raw_title, edit_url=href))
        return units

    def _create_lecture_unit(self, course_id: str, chapter: MarketplaceChapter, episode: Episode) -> MarketplaceUnit:
        edit_path = f'/marketplace/teacher/course/{course_id}/chapters/{chapter.id}/units/edit/?unit_type=lecture'
        soup = self._get_soup(edit_path)
        csrf = self._csrf_from_soup(soup)
        title = self._episode_form_title(episode)
        data = {'csrfmiddlewaretoken': (None, csrf), 'title': (None, title), 'description': (None, '')}
        subtitle_path = self._episode_subtitle_vtt_path(episode)
        files: dict[str, Any] = dict(data)
        file_handle = None
        try:
            if subtitle_path:
                file_handle = open(subtitle_path, 'rb')
                files['caption_file'] = (Path(subtitle_path).name, file_handle, 'text/vtt')
            response = self._post_form(edit_path, {}, files=files)
        finally:
            if file_handle:
                file_handle.close()
        location = response.headers.get('Location') or ''
        match = re.search(r'unit_id=(\d+)', location)
        if not match:
            raise UploadConfigurationError(f'Lecture unit was not created. redirect={location}')
        return MarketplaceUnit(id=match.group(1), title=title, edit_url=location)

    def _sync_unit_order(self, chapter: MarketplaceChapter, episodes: list[Episode]) -> None:
        units = self._list_units(chapter)
        if len(units) < 2:
            return

        episode_order: dict[str, int] = {}
        for index, episode in enumerate(sorted(episodes, key=lambda item: (item.episode_number or 0, item.sort_order or 0))):
            for title in self._episode_title_candidates(episode):
                normalized = self._normalize_title_text(title)
                if normalized:
                    episode_order[normalized] = index

        def unit_sort_key(unit: MarketplaceUnit) -> tuple[int, str]:
            unit_title = self._normalize_title_text(unit.title)
            for candidate, index in episode_order.items():
                if self._titles_match(unit_title, candidate):
                    return (index, unit.id)
            return (len(episode_order) + 1, unit.id)

        ordered_units = sorted(units, key=unit_sort_key)
        if [unit.id for unit in ordered_units] == [unit.id for unit in units]:
            return

        soup = self._get_soup(chapter.units_url)
        form = soup.find('form', {'id': 'units_orders'})
        if not form:
            return
        csrf = self._csrf_from_soup(BeautifulSoup(str(form), 'html.parser'))
        action = form.get('action') or f'{chapter.units_url.rstrip("/")}/submit_order/'
        data: list[tuple[str, str]] = [('csrfmiddlewaretoken', csrf)]
        data.extend(('pk_list', unit.id) for unit in ordered_units)
        response = self.session.post(
            self._absolute(action),
            headers=self._headers(accept='text/html', referer=self._absolute(chapter.units_url)) | {'X-CSRFToken': csrf},
            data=data,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        self._raise_for_response(response, self._absolute(action), allow_redirect=True)

    def _upload_video_to_unit(self, unit: MarketplaceUnit, video_path: str) -> dict[str, Any]:
        edit_url = self._absolute(unit.edit_url)
        if 'upload-only=true' not in edit_url:
            separator = '&' if '?' in edit_url else '?'
            edit_url = f'{edit_url}{separator}upload-only=true'
        soup = self._get_soup(edit_url)
        csrf = self._csrf_from_soup(soup)
        obj_id = self._script_value(soup, 'objId') or unit.id
        return self._upload_direct_video(
            referer_url=edit_url,
            video_path=video_path,
            upload_type='lecture',
            obj_id=obj_id,
            csrf=csrf,
            source='teacher',
            is_teaser=False,
        )

    def _upload_direct_video(
        self,
        *,
        referer_url: str,
        video_path: str,
        upload_type: str,
        obj_id: str,
        csrf: str,
        source: str,
        is_teaser: bool,
    ) -> dict[str, Any]:
        prepared = self._prepare_video_upload_file(video_path)
        upload_path = prepared['path']
        file_type = mimetypes.guess_type(upload_path)[0] or 'video/mp4'
        try:
            start = self.session.post(
                f'{self.base_url}/api/v1/general/upload/direct/start/',
                headers=self._headers(accept='application/json', referer=referer_url) | {'X-CSRFToken': csrf},
                data={
                    'csrfmiddlewaretoken': csrf,
                    'file_name': Path(video_path).name,
                    'file_type': file_type,
                    'type': upload_type,
                    'id': obj_id,
                    'source': source,
                    'is_teaser': 'true' if is_teaser else 'false',
                },
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            self._raise_for_response(start, f'{self.base_url}/api/v1/general/upload/direct/start/')
            start_payload = start.json()
            upload_url = start_payload['url']
            fields = start_payload['fields']
            file_id = start_payload['id']

            with open(upload_path, 'rb') as handle:
                upload = requests.post(
                    upload_url,
                    data=fields,
                    files={'file': (Path(video_path).name, handle, file_type)},
                    timeout=max(self.REQUEST_TIMEOUT_SECONDS, 900),
                )
            if upload.status_code >= 400:
                raise UploadConfigurationError(f'S3 video upload failed: {upload.status_code} {upload.text[:300]}')

            finish = self.session.post(
                f'{self.base_url}/api/v1/general/upload/direct/finish/',
                headers=self._headers(accept='application/json', referer=referer_url) | {'X-CSRFToken': csrf},
                data={'csrfmiddlewaretoken': csrf, 'file_id': file_id, 'type': upload_type, 'id': obj_id},
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            self._raise_for_response(finish, f'{self.base_url}/api/v1/general/upload/direct/finish/')
            return prepared
        finally:
            self._cleanup_prepared_upload_file(prepared)

    def _prepare_video_upload_file(self, video_path: str) -> dict[str, Any]:
        source_path = Path(video_path)
        if not source_path.is_file():
            raise UploadConfigurationError(f'Video file was not found before upload. path={video_path}')

        source_probe = extract_video_metadata(source_path)
        if not source_probe.get('ok'):
            raise UploadConfigurationError(
                f"Could not read local video metadata before upload. path={video_path} error={source_probe.get('error')}"
            )

        source_duration = probe_duration_seconds(source_probe)
        if source_duration is None:
            raise UploadConfigurationError(
                f'Local video duration is missing or zero before upload. path={video_path}'
            )

        prepared = {
            'path': str(source_path),
            'probe': source_probe,
            'source_probe': source_probe,
            'normalized': False,
            'temporary': False,
        }
        if source_path.suffix.lower() != '.mp4':
            return prepared

        remuxed = remux_mp4_for_upload(source_path)
        if remuxed.get('error') == 'ffmpeg_missing':
            return prepared
        if not remuxed.get('ok'):
            raise UploadConfigurationError(
                f"Could not normalize MP4 before upload. path={video_path} error={remuxed.get('error')}"
            )

        remuxed_probe = remuxed.get('metadata')
        remuxed_duration = probe_duration_seconds(remuxed_probe if isinstance(remuxed_probe, dict) else None)
        if remuxed_duration is None:
            temp_name = str(remuxed.get('path') or '').strip()
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)
            raise UploadConfigurationError(
                f'Normalized MP4 duration is missing or zero before upload. path={video_path}'
            )

        prepared.update(
            {
                'path': str(remuxed['path']),
                'probe': remuxed_probe,
                'normalized': True,
                'temporary': True,
            }
        )
        return prepared

    def _cleanup_prepared_upload_file(self, prepared: dict[str, Any]) -> None:
        if not prepared.get('temporary'):
            return
        temp_name = str(prepared.get('path') or '').strip()
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)

    def _csrf_from_soup(self, soup: BeautifulSoup) -> str:
        field = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if not field or not field.get('value'):
            raise UploadConfigurationError('CSRF token was not found on marketplace form.')
        return str(field.get('value'))

    def _script_value(self, soup: BeautifulSoup, name: str) -> str | None:
        scripts = '\n'.join(script.get_text('\n') for script in soup.find_all('script') if not script.get('src'))
        match = re.search(rf'var\s+{re.escape(name)}\s*=\s*[\'"]([^\'"]*)[\'"]', scripts)
        return match.group(1) if match else None

    def _script_bool_value(self, soup: BeautifulSoup, name: str, *, default: bool = False) -> bool:
        scripts = '\n'.join(script.get_text('\n') for script in soup.find_all('script') if not script.get('src'))
        match = re.search(rf'var\s+{re.escape(name)}\s*=\s*(true|false)', scripts, flags=re.IGNORECASE)
        if not match:
            return default
        return match.group(1).lower() == 'true'

    def _absolute(self, url_or_path: str) -> str:
        return urljoin(self.base_url, url_or_path)

    def _episode_form_title(self, episode: Episode) -> str:
        title_fa = (episode.title_fa or '').strip()
        if title_fa:
            return title_fa
        title_en = (episode.title_en or '').strip()
        if title_en:
            return title_en
        if episode.episode_number is not None:
            return f'Episode {episode.episode_number}'
        return 'Episode'

    def _episode_video_file_path(self, episode: Episode) -> str | None:
        local_video = (episode.video_local_path or '').strip()
        if not local_video:
            return None
        candidate = Path(local_video)
        if not candidate.is_file():
            return None
        return str(candidate.resolve())

    def _episode_subtitle_vtt_path(self, episode: Episode) -> str | None:
        candidates = [(episode.subtitle_processed_path or '').strip(), (episode.subtitle_local_path or '').strip()]
        for raw in candidates:
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.is_file() and candidate.suffix.lower() == '.vtt':
                return str(candidate.resolve())
        return None

    def _episode_title_candidates(self, episode: Episode) -> list[str]:
        candidates: list[str] = []
        title_fa = (episode.title_fa or '').strip()
        title_en = (episode.title_en or '').strip()
        if title_fa:
            candidates.append(title_fa)
        if title_en:
            candidates.append(title_en)
        if title_fa and title_en:
            candidates.append(f'{title_fa} ({title_en})')
            candidates.append(f'{title_fa}({title_en})')
        return candidates

    def _normalize_title_text(self, value: str) -> str:
        normalized = (value or '').strip().lower()
        normalized = normalized.replace('ي', 'ی').replace('ك', 'ک')
        normalized = re.sub(r'[\u200c\u200f\u202a-\u202e]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s\u0600-\u06FF\-\(\)]', '', normalized)
        return normalized.strip()

    def _titles_match(self, row_title: str, candidate: str) -> bool:
        if row_title == candidate:
            return True
        if len(candidate) >= 6 and candidate in row_title:
            return True
        if len(row_title) >= 6 and row_title in candidate:
            return True
        if min(len(row_title), len(candidate)) >= 6:
            return SequenceMatcher(None, row_title, candidate).ratio() >= 0.87
        return False


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join([f"'{part}'" for part in parts]) + ")"


class FirefoxUploadNavigator:
    PAGE_WAIT_SECONDS = 8
    ELEMENT_WAIT_SECONDS = 5
    FORM_WAIT_SECONDS = 10
    LOGIN_WAIT_SECONDS = 6
    SUBMIT_WAIT_SECONDS = 15
    UPLOAD_PAGE_WAIT_SECONDS = 30
    VIDEO_UPLOAD_WAIT_SECONDS = 1800
    VIDEO_UPLOAD_START_WAIT_SECONDS = 45
    VIDEO_UPLOAD_STABLE_POLLS = 3
    NAV_BACK_WAIT_SECONDS = 15
    TAB_WAIT_SECONDS = 6
    SEARCH_WAIT_SECONDS = 4
    PAGELOAD_TIMEOUT_SECONDS = 30
    PAGE_READY_WAIT_SECONDS = 20
    STEP_PAUSE_SECONDS = 1.2
    UNITS_LIST_WAIT_SECONDS = 15
    DEBUG_BROWSER_POOL_LIMIT = 5
    DEBUG_BROWSER_POOL: list[webdriver.Firefox] = []
    COURSE_UNITS_URL_CACHE: dict[str, str] = {}

    SETTINGS_KEYS = {
        'upload_firefox_headless',
        'upload_target_url',
        'upload_cookies_json',
        'upload_search_input_selector',
        'upload_course_result_xpath_template',
        'upload_sections_button_xpath',
        'upload_units_button_xpath',
        'upload_login_check_selector',
        'upload_episode_page_indicator_selector',
        'upload_firefox_geckodriver_path',
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = self._load_config()

    def validate_cookies(self) -> dict[str, Any]:
        return MirzaApiClient(self.config).validate_session()

    def open_course_episode_page(
        self,
        course: Course,
        episode: Episode,
        keep_browser_open: bool = False,
        preferred_units_url: str | None = None,
    ) -> dict[str, Any]:
        query = (course.title_fa or course.title_en or course.slug or '').strip()
        if not query:
            raise UploadConfigurationError('Course title is empty and cannot be used for search.')

        course_key = str(course.id)
        direct_units_url = (preferred_units_url or '').strip() or self.COURSE_UNITS_URL_CACHE.get(course_key)
        api_route = None if direct_units_url else self._resolve_course_route_with_api(course)
        landing_url = direct_units_url or (api_route.url if api_route else None)

        driver = self._create_driver()
        try:
            self._open_target_with_cookies(driver, landing_url=landing_url)
            self._assert_logged_in(driver)
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

            if direct_units_url and '/units/' in driver.current_url:
                units_list_url = self._derive_units_list_url(driver.current_url)
                if units_list_url:
                    self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url
                unit_route = self._open_or_create_episode_unit(driver, episode)
                unit_action = unit_route.get('unit_action')
                debug_halt = bool(keep_browser_open and unit_action == 'skip_existing')
                return {
                    'ok': True,
                    'query': query,
                    'current_url': driver.current_url,
                    'headless': self.config.headless,
                    'browser_kept_open': keep_browser_open,
                    'unit_action': unit_action,
                    'matched_unit_title': unit_route.get('matched_title'),
                    'editor_url': unit_route.get('editor_url', driver.current_url),
                    'units_list_url': units_list_url,
                    'used_cached_units_url': True,
                    'skip_existing': unit_action == 'skip_existing',
                    'debug_halt': debug_halt,
                    'should_continue': not debug_halt,
                    'form_filled': bool(unit_route.get('form_filled')),
                    'form_title': unit_route.get('form_title'),
                    'subtitle_attached': bool(unit_route.get('subtitle_attached')),
                    'subtitle_path': unit_route.get('subtitle_path'),
                    'subtitle_missing_reason': unit_route.get('subtitle_missing_reason'),
                }
            if api_route is not None:
                units_list_url = self._open_units_from_api_route(driver, course, api_route)
                if units_list_url:
                    self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url
                unit_route = self._open_or_create_episode_unit(driver, episode)
                unit_action = unit_route.get('unit_action')
                debug_halt = bool(keep_browser_open and unit_action == 'skip_existing')
                return {
                    'ok': True,
                    'query': query,
                    'current_url': driver.current_url,
                    'headless': self.config.headless,
                    'browser_kept_open': keep_browser_open,
                    'unit_action': unit_action,
                    'matched_unit_title': unit_route.get('matched_title'),
                    'editor_url': unit_route.get('editor_url', driver.current_url),
                    'units_list_url': units_list_url,
                    'used_cached_units_url': False,
                    'api_route_source': api_route.source,
                    'skip_existing': unit_action == 'skip_existing',
                    'debug_halt': debug_halt,
                    'should_continue': not debug_halt,
                    'form_filled': bool(unit_route.get('form_filled')),
                    'form_title': unit_route.get('form_title'),
                    'subtitle_attached': bool(unit_route.get('subtitle_attached')),
                    'subtitle_path': unit_route.get('subtitle_path'),
                    'subtitle_missing_reason': unit_route.get('subtitle_missing_reason'),
                }
            if direct_units_url and '/units/' not in driver.current_url:
                driver.get(self.config.target_url)
                self._assert_logged_in(driver)
                self._wait_for_page_ready(driver)
                self._pause_between_steps()

            wait = WebDriverWait(driver, self.PAGE_WAIT_SECONDS)
            search_input = None
            try:
                search_input = WebDriverWait(driver, self.SEARCH_WAIT_SECONDS).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, self.config.search_input_selector))
                )
            except TimeoutException:
                search_input = None

            if search_input is not None:
                search_input.click()
                search_input.send_keys(Keys.CONTROL, 'a')
                search_input.send_keys(Keys.DELETE)
                search_input.send_keys(query)
                search_input.send_keys(Keys.ENTER)

            if not self._find_and_click_course_chapters(driver, query):
                self._create_new_course(driver, course)
            self._ensure_chapters_have_units(driver, course)
            self._assert_logged_in(driver)
            self._click_units_button(driver)
            self._wait_for_units_listing_ready(driver)
            self._pause_between_steps()
            units_list_url = self._derive_units_list_url(driver.current_url)
            if units_list_url:
                self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url
            unit_route = self._open_or_create_episode_unit(driver, episode)

            if self.config.episode_page_indicator_selector:
                try:
                    wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, self.config.episode_page_indicator_selector)
                        )
                    )
                except TimeoutException as exc:
                    raise UploadConfigurationError(
                        f"Episode page indicator not found. selector={self.config.episode_page_indicator_selector} current_url={driver.current_url}"
                    ) from exc

            unit_action = unit_route.get('unit_action')
            debug_halt = bool(keep_browser_open and unit_action == 'skip_existing')
            return {
                'ok': True,
                'query': query,
                'current_url': driver.current_url,
                'headless': self.config.headless,
                'browser_kept_open': keep_browser_open,
                'unit_action': unit_action,
                'matched_unit_title': unit_route.get('matched_title'),
                'editor_url': unit_route.get('editor_url', driver.current_url),
                'units_list_url': units_list_url,
                'used_cached_units_url': False,
                'skip_existing': unit_action == 'skip_existing',
                'debug_halt': debug_halt,
                'should_continue': not debug_halt,
                'form_filled': bool(unit_route.get('form_filled')),
                'form_title': unit_route.get('form_title'),
                'subtitle_attached': bool(unit_route.get('subtitle_attached')),
                'subtitle_path': unit_route.get('subtitle_path'),
                'subtitle_missing_reason': unit_route.get('subtitle_missing_reason'),
            }
        finally:
            if keep_browser_open:
                self._retain_debug_browser(driver)
            else:
                driver.quit()

    def upload_course_episodes(
        self,
        course: Course,
        episodes: list[Episode],
        keep_browser_open: bool = False,
        preferred_units_url: str | None = None,
    ) -> dict[str, Any]:
        if not episodes:
            return {
                'ok': True,
                'query': (course.title_fa or course.title_en or course.slug or '').strip(),
                'headless': self.config.headless,
                'results': [],
                'processed_count': 0,
                'units_list_url': None,
                'used_cached_units_url': False,
            }

        query = (course.title_fa or course.title_en or course.slug or '').strip()
        if not query:
            raise UploadConfigurationError('Course title is empty and cannot be used for search.')

        route = self._resolve_course_route_with_api(course)
        return MaktabMarketplaceClient(self.config).upload_course_episodes(course, episodes, route)

        course_key = str(course.id)
        direct_units_url = (preferred_units_url or '').strip() or self.COURSE_UNITS_URL_CACHE.get(course_key)
        api_route = None if direct_units_url else self._resolve_course_route_with_api(course)
        landing_url = direct_units_url or (api_route.url if api_route else None)

        driver = self._create_driver()
        try:
            self._open_target_with_cookies(driver, landing_url=landing_url)
            self._assert_logged_in(driver)
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

            used_cached_units_url = False
            units_list_url = None
            if direct_units_url and '/units/' in driver.current_url:
                used_cached_units_url = True
                units_list_url = self._derive_units_list_url(driver.current_url)
            elif api_route is not None:
                units_list_url = self._open_units_from_api_route(driver, course, api_route)
            else:
                if direct_units_url and '/units/' not in driver.current_url:
                    driver.get(self.config.target_url)
                    self._assert_logged_in(driver)
                    self._wait_for_page_ready(driver)
                    self._pause_between_steps()

                wait = WebDriverWait(driver, self.PAGE_WAIT_SECONDS)
                search_input = None
                try:
                    search_input = WebDriverWait(driver, self.SEARCH_WAIT_SECONDS).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, self.config.search_input_selector))
                    )
                except TimeoutException:
                    search_input = None

                if search_input is not None:
                    search_input.click()
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    search_input.send_keys(query)
                    search_input.send_keys(Keys.ENTER)

                if not self._find_and_click_course_chapters(driver, query):
                    self._create_new_course(driver, course)
                self._ensure_chapters_have_units(driver, course)
                self._assert_logged_in(driver)
                self._click_units_button(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                units_list_url = self._derive_units_list_url(driver.current_url)

            if units_list_url:
                self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url

            results: list[dict[str, Any]] = []
            total = len(episodes)
            for index, episode in enumerate(episodes):
                should_return_to_list = index < total - 1
                try:
                    item = self._upload_episode_from_units_page(
                        driver,
                        episode,
                        should_return_to_list=should_return_to_list,
                        units_list_url=units_list_url,
                    )
                except UploadAuthExpiredError:
                    raise
                except UploadAutomationError as exc:
                    item = {
                        'episode_id': str(episode.id),
                        'episode_number': episode.episode_number,
                        'episode_title': (episode.title_fa or episode.title_en or '').strip(),
                        'result': 'error',
                        'unit_action': None,
                        'error': str(exc),
                        'form_filled': False,
                        'form_title': None,
                        'subtitle_attached': False,
                        'subtitle_path': None,
                        'subtitle_missing_reason': None,
                        'video_file': None,
                        'progress': None,
                        'returned_to_units': False,
                        'units_list_url': units_list_url,
                        'current_url': driver.current_url,
                    }
                    if should_return_to_list and units_list_url:
                        try:
                            driver.get(units_list_url)
                            if '/units/' in driver.current_url:
                                self._wait_for_page_ready(driver)
                                self._wait_for_units_listing_ready(driver)
                                self._pause_between_steps()
                                item['returned_to_units'] = True
                                item['current_url'] = driver.current_url
                        except Exception:
                            pass
                results.append(item)
                if item.get('units_list_url') and not units_list_url:
                    units_list_url = str(item.get('units_list_url'))
                    self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url

            return {
                'ok': True,
                'query': query,
                'headless': self.config.headless,
                'current_url': driver.current_url,
                'browser_kept_open': keep_browser_open,
                'results': results,
                'processed_count': len(results),
                'units_list_url': units_list_url,
                'used_cached_units_url': used_cached_units_url,
                'api_route_source': api_route.source if api_route else None,
            }
        finally:
            if keep_browser_open:
                self._retain_debug_browser(driver)
            else:
                driver.quit()

    def _pause_between_steps(self, seconds: float | None = None) -> None:
        time.sleep(seconds if seconds is not None else self.STEP_PAUSE_SECONDS)

    def _resolve_course_route_with_api(self, course: Course) -> MirzaCourseRoute | None:
        client = MirzaApiClient(self.config)
        route = client.resolve_course_route(course, self._titles_match)
        return route

    def _open_units_from_api_route(
        self,
        driver: webdriver.Firefox,
        course: Course,
        route: MirzaCourseRoute,
    ) -> str | None:
        if route.created:
            self._fill_course_details_form(driver, course)

        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))

        if '/units/' not in (driver.current_url or ''):
            if '/chapters/' not in (driver.current_url or ''):
                chapters_url = self._course_chapters_url_from_route(route)
                if chapters_url:
                    driver.get(chapters_url)
                    self._wait_for_page_ready(driver)
                    self._pause_between_steps()
            if '/chapters/' not in (driver.current_url or ''):
                self._click_sections_button(driver)

            self._ensure_chapters_have_units(driver, course)
            self._assert_logged_in(driver)
            self._click_units_button(driver)

        self._wait_for_units_listing_ready(driver)
        self._pause_between_steps()
        return self._derive_units_list_url(driver.current_url)

    def _course_chapters_url_from_route(self, route: MirzaCourseRoute) -> str | None:
        if '/chapters/' in route.url:
            return route.url
        if route.course_id:
            return urljoin(self.config.target_url, f'/courses/{route.course_id}/chapters/')
        match = re.search(r'/courses/([^/]+)/', route.url)
        if match:
            return urljoin(self.config.target_url, f'/courses/{match.group(1)}/chapters/')
        return None

    def _wait_for_page_ready(self, driver: webdriver.Firefox, timeout: float | None = None) -> None:
        wait_seconds = timeout if timeout is not None else self.PAGE_READY_WAIT_SECONDS
        try:
            WebDriverWait(driver, wait_seconds, poll_frequency=0.2).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except (TimeoutException, WebDriverException):
            return

    def _wait_for_units_listing_ready(self, driver: webdriver.Firefox) -> None:
        if '/units/' not in (driver.current_url or ''):
            return

        try:
            WebDriverWait(driver, self.UNITS_LIST_WAIT_SECONDS, poll_frequency=0.3).until(
                lambda d: bool(d.find_elements(By.CSS_SELECTOR, 'li.item'))
                or bool(d.find_elements(By.XPATH, "//a[contains(@href, 'unit_type=lecture')]"))
            )
        except TimeoutException:
            return

    def _click_sections_button(self, driver: webdriver.Firefox) -> None:
        if self._try_click_sections_button(driver):
            return

        raise UploadConfigurationError(
            f"Sections button not found. sections_xpath={self.config.sections_button_xpath} current_url={driver.current_url}"
        )

    def _find_and_click_course_chapters(self, driver: webdriver.Firefox, query: str) -> bool:
        self._pause_between_steps(1)
        try:
            WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".my-16"))
            )
        except TimeoutException:
            pass

        containers = driver.find_elements(By.CSS_SELECTOR, ".my-16, .my-8, .p-4 > div > div > div")
        for container in containers:
            try:
                title_el = container.find_element(By.CSS_SELECTOR, ".mt-4, .font-bold.text-black")
                title_text = (title_el.text or "").strip()
                if self._titles_match(self._normalize_title_text(title_text), self._normalize_title_text(query)):
                    # Instead of relying on nth-child or sibling selectors like .mx-4~ .mx-4+ .mx-4,
                    # just find the button that links to /chapters/
                    btn = None
                    links = container.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        href = link.get_attribute("href") or ""
                        text = (link.text or "").strip()
                        if "/chapters/" in href or "فصل" in text:
                            btn = link
                            break
                    
                    if btn:
                        before_handles = set(driver.window_handles)
                        self._safe_click(driver, btn)
                        self._switch_to_new_tab(driver, before_handles)
                        return True
            except WebDriverException:
                continue

        # Fallback to older matching logic in case UI differs
        try:
            result_xpath = self._build_result_xpath(query)
            try:
                course_entry = driver.find_element(By.XPATH, result_xpath)
            except WebDriverException:
                course_entry = None
                
            if course_entry:
                course_entry.click()
                if self._try_click_sections_button(driver):
                    return True
        except WebDriverException:
            pass

        return False

    def _create_new_course(self, driver: webdriver.Firefox, course: Course) -> None:
        """Create a brand new course draft and navigate to its /chapters/ page."""
        create_locators = [
            (By.XPATH, "//a[contains(@href, '/create-draft') or contains(@href, '/courses/create-draft')]"),
            (By.XPATH, "//a[contains(normalize-space(.), 'ساخت دوره جدید')]"),
        ]
        
        create_btn = None
        wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)
        for by, value in create_locators:
            try:
                create_btn = wait.until(EC.element_to_be_clickable((by, value)))
                break
            except TimeoutException:
                continue
                
        if not create_btn:
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            raise UploadConfigurationError(
                f"Course not found, and 'Create Draft' (ساخت دوره جدید) button was not found on the page. current_url={driver.current_url}"
            )
            
        before_handles = set(driver.window_handles)
        self._safe_click(driver, create_btn)
        self._switch_to_new_tab(driver, before_handles)
        
        self._wait_for_page_ready(driver)
        self._pause_between_steps()

        # --- Step 1: Fill the initial create-draft form (title + category) ---
        # This page has #title and #main_category
        try:
            title_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#title"))
            )
            title = (course.title_fa or course.title_en or '').strip()
            title_input.click()
            title_input.send_keys(Keys.CONTROL, 'a')
            title_input.send_keys(Keys.DELETE)
            title_input.send_keys(title)
            
            # Open category dropdown
            try:
                category_dropdown = driver.find_element(By.CSS_SELECTOR, "#main_category")
                self._safe_click(driver, category_dropdown)
                self._pause_between_steps(0.5)
                
                try:
                    menu_container = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".z-50"))
                    )
                    for _ in range(4):
                        driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", menu_container)
                        driver.execute_script("""
                            var uls = arguments[0].getElementsByTagName('ul');
                            if(uls.length > 0) uls[0].scrollTo(0, uls[0].scrollHeight);
                        """, menu_container)
                        time.sleep(0.4)
                except TimeoutException:
                    pass

                menu_options = driver.find_elements(By.CSS_SELECTOR, ".z-50 li, .z-50 .cursor-pointer, .z-50 a, .z-50 div[role='option']")
                best_option = None
                for option in menu_options:
                    if not option.is_displayed():
                        continue
                    if best_option is None:
                        best_option = option
                    opt_text = (option.text or "").strip()
                    if opt_text and self._titles_match(self._normalize_title_text(opt_text), self._normalize_title_text(title)):
                        best_option = option
                        break
                if best_option:
                    self._safe_click(driver, best_option)
            except WebDriverException:
                pass

            # Click the continue/submit button on the create-draft page
            self._pause_between_steps(0.5)
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, ".\\!rounded-lg")
            except WebDriverException:
                submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            self._pause_between_steps(0.3)
            self._safe_click(driver, submit_btn)
            
            self._pause_between_steps(2.0)
            self._wait_for_page_ready(driver)
        except (TimeoutException, WebDriverException):
            pass

        # --- Step 2: Fill the course details form (description, image, etc.) ---
        # After submitting the create-draft form, MaktabKhooneh redirects to the
        # full course editing page. Check if we are on that page.
        self._fill_course_details_form(driver, course)

        # --- Step 3: Navigate to chapters page ---
        # After saving course details, we need to get to /chapters/.
        # First check if we are already there.
        current = driver.current_url or ''
        if '/chapters/' not in current:
            # Try to find and click the sections button on the current page
            try:
                self._click_sections_button(driver)
            except UploadConfigurationError:
                # If sections button not found, maybe we need to go back to course list
                # and find the course we just created
                driver.get(self.config.target_url)
                self._wait_for_page_ready(driver)
                self._pause_between_steps()
                query = (course.title_fa or course.title_en or '').strip()
                search_input = None
                try:
                    search_input = WebDriverWait(driver, self.SEARCH_WAIT_SECONDS).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, self.config.search_input_selector))
                    )
                except TimeoutException:
                    pass
                if search_input:
                    search_input.click()
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    search_input.send_keys(query)
                    search_input.send_keys(Keys.ENTER)
                if not self._find_and_click_course_chapters(driver, query):
                    raise UploadConfigurationError(
                        f"Created course but could not navigate to its chapters page. current_url={driver.current_url}"
                    )

    def _fill_course_details_form(self, driver: webdriver.Firefox, course: Course) -> None:
        """Fill the course details form if we are on it (description, prereqs, image, etc.)."""
        title = (course.title_fa or course.title_en or '').strip()
        
        # Check if description iframe exists (indicates we are on the details form)
        try:
            desc_iframe = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#id_description_ifr"))
            )
        except TimeoutException:
            # Not on the details form page, skip
            return

        # Fill description
        try:
            driver.switch_to.frame(desc_iframe)
            desc_body = driver.find_element(By.TAG_NAME, "body")
            desc_body.clear()
            course_desc = getattr(course, 'description_fa', '') or getattr(course, 'description_en', '')
            desc_body.send_keys(title + " - این دوره به صورت خودکار ایجاد شده است.\n\n" + (course_desc or "توضیحات دوره"))
            driver.switch_to.default_content()
        except WebDriverException:
            driver.switch_to.default_content()

        # Fill prerequisite description
        try:
            pre_iframe = driver.find_element(By.CSS_SELECTOR, "#id_prerequisite_description_ifr")
            driver.switch_to.frame(pre_iframe)
            pre_body = driver.find_element(By.TAG_NAME, "body")
            pre_body.clear()
            pre_body.send_keys("ندارد")
            driver.switch_to.default_content()
        except WebDriverException:
            driver.switch_to.default_content()

        # Cover Image
        try:
            cover_input = driver.find_element(By.CSS_SELECTOR, "#id_image")
            local_cover = getattr(course, 'cover_local_path', '') or ''
            local_cover = local_cover.strip()
            if local_cover and Path(local_cover).is_file():
                cover_input.send_keys(str(Path(local_cover).resolve()))
                # Give the image time to upload asynchronously before moving on
                self._pause_between_steps(4.0)
        except WebDriverException:
            pass
                
        # What you'll learn items
        try:
            learn_inputs = driver.find_elements(By.CSS_SELECTOR, "input.top-margin[name='learning_goals']")
            learn_texts = ["تسلط به مفاهیم پایه", "انجام پروژه‌های عملی", "آمادگی برای بازار کار", "دریافت گواهینامه معتبر"]
            for i, learn_input in enumerate(learn_inputs[:4]):
                learn_input.clear()
                learn_input.send_keys(learn_texts[i % len(learn_texts)])
        except WebDriverException:
            pass
                
        # Teaser Video
        try:
            teaser_input = driver.find_element(By.CSS_SELECTOR, "#file_upload")
            local_teaser = getattr(course, 'teaser_local_path', '') or ''
            local_teaser = local_teaser.strip()
            if local_teaser and Path(local_teaser).is_file():
                teaser_input.send_keys(str(Path(local_teaser).resolve()))
                try:
                    WebDriverWait(driver, self.VIDEO_UPLOAD_START_WAIT_SECONDS, poll_frequency=0.5).until(
                        lambda d: self._has_video_upload_started(d)
                    )
                    stable_polls = 0
                    deadline = time.time() + self.VIDEO_UPLOAD_WAIT_SECONDS
                    while time.time() < deadline:
                        if self._is_video_upload_complete(driver):
                            stable_polls += 1
                            if stable_polls >= self.VIDEO_UPLOAD_STABLE_POLLS:
                                self._pause_between_steps(1)
                                break
                        else:
                            stable_polls = 0
                        time.sleep(1)
                except TimeoutException:
                    pass
        except WebDriverException:
            pass

        # Save form
        self._pause_between_steps(1)
        try:
            submit_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".mirza-form__button--sticky"))
            )
        except TimeoutException:
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except WebDriverException:
                return
                
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
        self._pause_between_steps(0.5)
        self._safe_click(driver, submit_btn)
        
        self._pause_between_steps(2.0)
        self._wait_for_page_ready(driver)

    def _ensure_chapters_have_units(self, driver: webdriver.Firefox, course: Course) -> None:
        """Make sure we are on /chapters/ and that at least one chapter exists.
        If no chapter exists, create one. After that, a /units/ link should be available."""
        current_url = driver.current_url or ''
        
        # If we're already on /units/, nothing to do
        if '/units/' in current_url:
            return
        
        # If we're not on /chapters/, we can't do anything here
        if '/chapters/' not in current_url:
            return
            
        self._pause_between_steps(0.5)
        self._wait_for_page_ready(driver)
        
        # Check if /units/ links exist (means chapters already have content)
        units_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/units/')]")
        if units_links:
            return  # Chapters exist, units page is reachable
        
        # No units links found - need to create a chapter
        self._create_first_chapter(driver, course)

    def _create_first_chapter(self, driver: webdriver.Firefox, course: Course) -> None:
        """Create the first chapter (سرفصل) for a course that has none."""
        self._pause_between_steps(1)
        self._wait_for_page_ready(driver)
        
        # Double-check: if /units/ links now exist, skip
        try:
            if driver.find_elements(By.XPATH, "//a[contains(@href, '/units/')]"):
                return
        except WebDriverException:
            pass

        # Look for the add-chapter button
        add_chapter_btn = None
        try:
            # Try specific button text first
            buttons = driver.find_elements(By.CSS_SELECTOR, ".mirza-form__button")
            for btn in buttons:
                btn_text = (btn.text or '').strip()
                # Accept button if it contains chapter-related text or is the only button
                if 'فصل' in btn_text or 'سرفصل' in btn_text or 'اضافه' in btn_text or len(buttons) == 1:
                    add_chapter_btn = btn
                    break
            if not add_chapter_btn and buttons:
                add_chapter_btn = buttons[0]
        except WebDriverException:
            pass

        if not add_chapter_btn:
            return  # No add-chapter button found, nothing we can do

        before_handles = set(driver.window_handles)
        self._safe_click(driver, add_chapter_btn)
        self._switch_to_new_tab(driver, before_handles)
        self._wait_for_page_ready(driver)
        self._pause_between_steps(0.5)
        
        # Fill out the chapter title
        try:
            title_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#id_title"))
            )
            title_input.clear()
            chapter_name = "محتوای دوره"
            title_input.send_keys(chapter_name)
        except (TimeoutException, WebDriverException):
            return  # Can't fill title, give up
        
        # Save the chapter
        try:
            save_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".mirza-form__button--sticky"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", save_btn)
            self._pause_between_steps(0.5)
            self._safe_click(driver, save_btn)
            
            self._pause_between_steps(2.0)
            self._wait_for_page_ready(driver)
        except (TimeoutException, WebDriverException):
            pass
        
        # After saving, MaktabKhooneh should redirect back to /chapters/ listing
        # Verify we're back on /chapters/ and /units/ links are now available
        self._pause_between_steps(1)
        current = driver.current_url or ''
        if '/chapters/' not in current and '/units/' not in current:
            # Try going back
            driver.back()
            self._wait_for_page_ready(driver)
            self._pause_between_steps(1)

    def _try_click_sections_button(self, driver: webdriver.Firefox) -> bool:
        before_handles = set(driver.window_handles)
        short_wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)
        locators = [
            (By.XPATH, self.config.sections_button_xpath),
            (
                By.XPATH,
                "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'ÙØµÙ„') and contains(normalize-space(.), 'Ø¬Ù„Ø³')]",
            ),
            (By.XPATH, "//a[contains(@href, '/chapters/')]"),
        ]

        for by, value in locators:
            try:
                button = short_wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            try:
                button.click()
            except WebDriverException:
                driver.execute_script('arguments[0].click();', button)

            self._switch_to_new_tab(driver, before_handles)
            return True

        return False

    def _switch_to_new_tab(self, driver: webdriver.Firefox, before_handles: set[str]) -> None:
        try:
            WebDriverWait(driver, self.TAB_WAIT_SECONDS).until(lambda d: len(d.window_handles) > len(before_handles))
        except TimeoutException:
            return

        after_handles = set(driver.window_handles)
        new_handles = [handle for handle in after_handles if handle not in before_handles]
        if new_handles:
            driver.switch_to.window(new_handles[-1])
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

    def _click_units_button(self, driver: webdriver.Firefox) -> None:
        before_handles = set(driver.window_handles)
        locators = [
            (By.XPATH, self.config.units_button_xpath),
            (By.XPATH, "//a[contains(@href, '/units/')]"),
        ]
        short_wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)

        for by, value in locators:
            try:
                button = short_wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            try:
                button.click()
            except WebDriverException:
                driver.execute_script('arguments[0].click();', button)

            self._switch_to_new_tab(driver, before_handles)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(
                    self._auth_expired_message(driver.current_url)
                )
            try:
                WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS).until(lambda d: '/units/' in d.current_url)
            except TimeoutException:
                raise UploadConfigurationError(
                    f"Units link clicked but units page did not open. current_url={driver.current_url}"
                )
            self._wait_for_page_ready(driver)
            self._wait_for_units_listing_ready(driver)
            self._pause_between_steps()
            return

        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(
                self._auth_expired_message(driver.current_url)
            )
        raise UploadConfigurationError(
            f"Units edit link not found. units_xpath={self.config.units_button_xpath} current_url={driver.current_url}"
        )

    def _open_or_create_episode_unit(self, driver: webdriver.Firefox, episode: Episode) -> dict[str, Any]:
        self._wait_for_units_listing_ready(driver)
        self._pause_between_steps(0.6)
        candidates = [self._normalize_title_text(item) for item in self._episode_title_candidates(episode)]
        candidates = [item for item in candidates if item]

        rows = driver.find_elements(By.CSS_SELECTOR, 'li.item')
        for row in rows:
            title_elements = row.find_elements(By.CSS_SELECTOR, '.ellipsis')
            if not title_elements:
                continue

            raw_title = (title_elements[0].get_attribute('title') or title_elements[0].text or '').strip()
            row_title = self._normalize_title_text(raw_title)
            if not row_title:
                continue
            if not any(self._titles_match(row_title, candidate) for candidate in candidates):
                continue

            detail_links = row.find_elements(By.XPATH, ".//a[contains(@href, '/units/edit/?unit_id=')]")
            detail_href = detail_links[0].get_attribute('href') if detail_links else None

            return {
                'unit_action': 'skip_existing',
                'matched_title': raw_title,
                'editor_url': urljoin(driver.current_url, detail_href) if detail_href else None,
                'form_filled': False,
                'form_title': None,
                'subtitle_attached': False,
                'subtitle_path': None,
                'subtitle_missing_reason': 'existing_unit',
            }

        create_locators = [
            (By.XPATH, "//a[contains(@href, 'unit_type=lecture') and contains(normalize-space(.), 'جلسه')]"),
            (By.XPATH, "//a[contains(@href, 'unit_type=lecture')]"),
            (By.XPATH, "//a[contains(normalize-space(.), 'درس جدید')]"),
            (By.XPATH, "//a[contains(normalize-space(.), 'اضافه کردن جلسه')]"),
            (By.CSS_SELECTOR, "a.mirza-button--primary[href*='unit_type=lecture']"),
            (By.XPATH, "//a[contains(@href, '/units/create-draft') or contains(@href, 'create')]"),
        ]
        wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)
        for by, value in create_locators:
            try:
                create_button = wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            before_handles = set(driver.window_handles)
            self._safe_click(driver, create_button)
            self._switch_to_new_tab(driver, before_handles)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            try:
                WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS).until(
                    lambda d: '/units/edit/' in d.current_url or 'unit_type=lecture' in d.current_url
                )
            except TimeoutException as exc:
                raise UploadConfigurationError(
                    f'Create lecture page did not open. current_url={driver.current_url}'
                ) from exc
            self._wait_for_page_ready(driver)
            self._pause_between_steps()
            form_result = self._populate_episode_form(driver, episode)

            return {
                'unit_action': 'create_new',
                'matched_title': None,
                'editor_url': driver.current_url,
                'form_filled': form_result.get('form_filled', False),
                'form_title': form_result.get('form_title'),
                'subtitle_attached': form_result.get('subtitle_attached', False),
                'subtitle_path': form_result.get('subtitle_path'),
                'subtitle_missing_reason': form_result.get('subtitle_missing_reason'),
            }

        raise UploadConfigurationError(
            f'No matching unit found and create button is missing. current_url={driver.current_url}'
        )

    def _upload_episode_from_units_page(
        self,
        driver: webdriver.Firefox,
        episode: Episode,
        should_return_to_list: bool,
        units_list_url: str | None,
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {
            'episode_id': str(episode.id),
            'episode_number': episode.episode_number,
            'episode_title': (episode.title_fa or episode.title_en or '').strip(),
            'result': 'error',
            'unit_action': None,
            'error': None,
            'form_filled': False,
            'form_title': None,
            'subtitle_attached': False,
            'subtitle_path': None,
            'subtitle_missing_reason': None,
            'video_file': None,
            'progress': None,
            'returned_to_units': False,
            'units_list_url': units_list_url,
            'current_url': driver.current_url,
        }

        unit_route = self._open_or_create_episode_unit(driver, episode)
        unit_action = unit_route.get('unit_action')
        outcome['unit_action'] = unit_action
        outcome['current_url'] = driver.current_url
        outcome['form_filled'] = bool(unit_route.get('form_filled'))
        outcome['form_title'] = unit_route.get('form_title')
        outcome['subtitle_attached'] = bool(unit_route.get('subtitle_attached'))
        outcome['subtitle_path'] = unit_route.get('subtitle_path')
        outcome['subtitle_missing_reason'] = unit_route.get('subtitle_missing_reason')
        outcome['units_list_url'] = self._derive_units_list_url(driver.current_url) or units_list_url

        if unit_action == 'skip_existing':
            outcome['result'] = 'skipped_existing'
            return outcome

        self._submit_episode_changes(driver)
        video_file = self._episode_video_file_path(episode)
        outcome['video_file'] = video_file
        if not video_file:
            outcome['result'] = 'skipped_missing_video'
            outcome['error'] = 'Video file was not found for this episode.'
            if should_return_to_list:
                self._return_to_units_list(driver, outcome.get('units_list_url'))
                outcome['returned_to_units'] = '/units/' in driver.current_url
                outcome['current_url'] = driver.current_url
            return outcome

        self._attach_video_file_and_wait(driver, video_file)
        outcome['progress'] = '100%'
        outcome['result'] = 'uploaded'

        if should_return_to_list:
            self._return_to_units_list(driver, outcome.get('units_list_url'))
            outcome['returned_to_units'] = '/units/' in driver.current_url
            outcome['current_url'] = driver.current_url

        return outcome

    def _submit_episode_changes(self, driver: webdriver.Firefox) -> None:
        wait = WebDriverWait(driver, self.SUBMIT_WAIT_SECONDS)
        locators = [
            (By.CSS_SELECTOR, "button.mirza-form__button--sticky[type='submit']"),
            (By.XPATH, "//button[@type='submit' and contains(normalize-space(.), 'ثبت تغییرات')]"),
            (By.XPATH, "//button[@type='submit']"),
        ]
        submit_button = None
        for by, value in locators:
            try:
                submit_button = wait.until(EC.element_to_be_clickable((by, value)))
                break
            except TimeoutException:
                continue

        if submit_button is None:
            raise UploadConfigurationError(
                f'Submit button (ثبت تغییرات) was not found on episode form. current_url={driver.current_url}'
            )

        self._safe_click(driver, submit_button)
        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
        self._wait_for_page_ready(driver)
        self._pause_between_steps()

    def _attach_video_file_and_wait(self, driver: webdriver.Firefox, video_path: str) -> None:
        file_input = self._wait_for_video_upload_input(driver)
        self._pause_between_steps(0.8)
        try:
            file_input.send_keys(video_path)
        except WebDriverException as exc:
            raise UploadConfigurationError(
                f'Failed to attach video file. path={video_path} current_url={driver.current_url}'
            ) from exc

        try:
            WebDriverWait(driver, self.VIDEO_UPLOAD_START_WAIT_SECONDS, poll_frequency=0.5).until(
                lambda d: self._has_video_upload_started(d)
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Video upload did not start after attaching file. current_url={driver.current_url}'
            ) from exc

        stable_polls = 0
        deadline = time.time() + self.VIDEO_UPLOAD_WAIT_SECONDS
        while time.time() < deadline:
            if self._is_video_upload_complete(driver):
                stable_polls += 1
                if stable_polls >= self.VIDEO_UPLOAD_STABLE_POLLS:
                    self._pause_between_steps(1)
                    return
            else:
                stable_polls = 0
            time.sleep(1)

        raise UploadConfigurationError(
            f'Video upload did not reach stable 100% before timeout. current_url={driver.current_url}'
        )

    def _wait_for_video_upload_input(self, driver: webdriver.Firefox) -> Any:
        selectors = [
            'input#file_upload',
            "input[type='file']#file_upload",
            "input[type='file'][id='file_upload']",
        ]
        wait = WebDriverWait(driver, self.UPLOAD_PAGE_WAIT_SECONDS)
        try:
            return wait.until(
                lambda d: next(
                    (
                        element
                        for selector in selectors
                        for elements in [d.find_elements(By.CSS_SELECTOR, selector)]
                        for element in elements
                        if element.is_enabled()
                    ),
                    False,
                )
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Video upload input (#file_upload) not found after saving episode. current_url={driver.current_url}'
            ) from exc

    def _upload_progress_percent(self, driver: webdriver.Firefox) -> float | None:
        value_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-value')
        for element in value_elements:
            text = self._normalize_digits((element.text or '').strip()).replace('٪', '%')
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
            if text.isdigit():
                try:
                    return float(text)
                except ValueError:
                    continue

        bar_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-bar')
        for element in bar_elements:
            style = self._normalize_digits((element.get_attribute('style') or '').strip())
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', style)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def _has_video_upload_started(self, driver: webdriver.Firefox) -> bool:
        percent = self._upload_progress_percent(driver)
        if percent is not None and percent > 0:
            return True

        file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input#file_upload')
        for element in file_inputs:
            value = (element.get_attribute('value') or '').strip()
            if value:
                return True
        return False

    def _is_video_upload_complete(self, driver: webdriver.Firefox) -> bool:
        percent = self._upload_progress_percent(driver)
        if percent is not None and percent >= 100:
            return True

        value_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-value')
        for element in value_elements:
            text = self._normalize_digits((element.text or '').strip()).replace('٪', '%')
            if '100%' in text or text == '100':
                return True

        bar_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-bar')
        for element in bar_elements:
            style = self._normalize_digits((element.get_attribute('style') or '').strip())
            if '100%' in style:
                return True
        return False

    def _return_to_units_list(self, driver: webdriver.Firefox, units_list_url: str | None) -> None:
        locators = [
            (By.XPATH, "//a[contains(@href, '/units/') and contains(normalize-space(.), 'بازگشت')]"),
            (By.CSS_SELECTOR, "a.mirza-form__button[href*='/units/']"),
            (By.XPATH, "//a[contains(@href, '/units/')]"),
        ]
        wait = WebDriverWait(driver, self.NAV_BACK_WAIT_SECONDS)
        for by, value in locators:
            try:
                back_link = wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            self._safe_click(driver, back_link)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            try:
                WebDriverWait(driver, self.NAV_BACK_WAIT_SECONDS).until(lambda d: '/units/' in d.current_url)
                self._wait_for_page_ready(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                return
            except TimeoutException:
                continue

        if units_list_url:
            driver.get(units_list_url)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            if '/units/' in driver.current_url:
                self._wait_for_page_ready(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                return

        raise UploadConfigurationError(
            f'Could not navigate back to units list after video upload. current_url={driver.current_url}'
        )

    def _normalize_digits(self, value: str) -> str:
        if not value:
            return value
        return value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))

    def _populate_episode_form(self, driver: webdriver.Firefox, episode: Episode) -> dict[str, Any]:
        title_value = self._episode_form_title(episode)
        wait = WebDriverWait(driver, self.FORM_WAIT_SECONDS)
        try:
            title_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#id_title,input[name='title']"))
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Title input was not found on episode form. current_url={driver.current_url}'
            ) from exc

        title_input.click()
        title_input.send_keys(Keys.CONTROL, 'a')
        title_input.send_keys(Keys.DELETE)
        title_input.send_keys(title_value)

        subtitle_path = self._episode_subtitle_vtt_path(episode)
        if not subtitle_path:
            return {
                'form_filled': True,
                'form_title': title_value,
                'subtitle_attached': False,
                'subtitle_path': None,
                'subtitle_missing_reason': 'processed_vtt_not_found',
            }

        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input#id_caption_file,input[name='caption_file']")
        if not file_inputs:
            return {
                'form_filled': True,
                'form_title': title_value,
                'subtitle_attached': False,
                'subtitle_path': subtitle_path,
                'subtitle_missing_reason': 'caption_input_not_found',
            }
        try:
            file_inputs[0].send_keys(subtitle_path)
        except WebDriverException as exc:
            raise UploadConfigurationError(
                f'Failed to attach VTT subtitle file. path={subtitle_path} current_url={driver.current_url}'
            ) from exc

        return {
            'form_filled': True,
            'form_title': title_value,
            'subtitle_attached': True,
            'subtitle_path': subtitle_path,
            'subtitle_missing_reason': None,
        }

    def _episode_form_title(self, episode: Episode) -> str:
        title_fa = (episode.title_fa or '').strip()
        if title_fa:
            return title_fa

        title_en = (episode.title_en or '').strip()
        if title_en:
            return title_en

        if episode.episode_number is not None:
            return f'Episode {episode.episode_number}'
        return 'Episode'

    def _episode_subtitle_vtt_path(self, episode: Episode) -> str | None:
        candidates: list[str] = []
        processed = (episode.subtitle_processed_path or '').strip()
        local_subtitle = (episode.subtitle_local_path or '').strip()

        if processed:
            candidates.append(processed)
        if local_subtitle:
            candidates.append(local_subtitle)

        for raw in candidates:
            candidate = Path(raw)
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() != '.vtt':
                continue
            return str(candidate.resolve())
        return None

    def _episode_video_file_path(self, episode: Episode) -> str | None:
        local_video = (episode.video_local_path or '').strip()
        if not local_video:
            return None
        candidate = Path(local_video)
        if not candidate.is_file():
            return None
        return str(candidate.resolve())

    def _episode_title_candidates(self, episode: Episode) -> list[str]:
        candidates: list[str] = []
        title_fa = (episode.title_fa or '').strip()
        title_en = (episode.title_en or '').strip()

        if title_fa:
            candidates.append(title_fa)
        if title_en:
            candidates.append(title_en)
        if title_fa and title_en:
            candidates.append(f'{title_fa} ({title_en})')
            candidates.append(f'{title_fa}({title_en})')

        return candidates

    def _normalize_title_text(self, value: str) -> str:
        normalized = (value or '').strip().lower()
        normalized = normalized.replace('ي', 'ی').replace('ك', 'ک')
        normalized = re.sub(r'[\u200c\u200f\u202a-\u202e]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s\u0600-\u06FF\-\(\)]', '', normalized)
        return normalized.strip()

    def _titles_match(self, row_title: str, candidate: str) -> bool:
        if row_title == candidate:
            return True
        if len(candidate) >= 6 and candidate in row_title:
            return True
        if len(row_title) >= 6 and row_title in candidate:
            return True
        if min(len(row_title), len(candidate)) >= 6:
            ratio = SequenceMatcher(None, row_title, candidate).ratio()
            if ratio >= 0.87:
                return True
        return False

    def _safe_click(self, driver: webdriver.Firefox, element: Any) -> None:
        try:
            element.click()
        except WebDriverException:
            driver.execute_script('arguments[0].click();', element)
        self._pause_between_steps(0.6)

    def _build_result_xpath(self, query: str) -> str:
        template = self.config.course_result_xpath_template
        if '{query}' not in template:
            return template
        return template.replace('{query}', _xpath_literal(query))

    def _derive_units_list_url(self, current_url: str) -> str | None:
        if '/units/' not in (current_url or ''):
            return None
        parts = urlsplit(current_url)
        path = parts.path or '/'
        marker = '/units/'
        marker_index = path.find(marker)
        if marker_index < 0:
            return None
        units_path = path[: marker_index + len(marker)]
        if not units_path.endswith('/'):
            units_path = f'{units_path}/'
        return f'{parts.scheme}://{parts.netloc}{units_path}'

    def _open_target_with_cookies(self, driver: webdriver.Firefox, landing_url: str | None = None) -> None:
        cookies = self._parse_cookies(self.config.cookies_json)
        if not cookies:
            raise UploadConfigurationError('No cookies configured. Please provide valid cookies in admin settings.')

        target_parts = urlsplit(self.config.target_url)
        target_host = (target_parts.hostname or '').strip()
        if not target_host:
            raise UploadConfigurationError('upload_target_url is invalid. Host is missing.')
        target_scheme = target_parts.scheme if target_parts.scheme in {'http', 'https'} else 'https'
        if not self._has_cookie_for_target_host(cookies, target_host):
            raise UploadConfigurationError(
                f'No cookie domain matches target host "{target_host}". '
                'Export cookies while logged in on maktabkhooneh/mirza and save them in upload_cookies_json.'
            )

        applied = 0
        current_seed_url = None
        for cookie in cookies:
            payload = self._normalize_cookie(cookie)
            if not payload.get('name') or payload.get('value') is None:
                continue

            cookie_host = str(payload.get('domain') or '').strip().lstrip('.') or target_host
            seed_scheme = 'https' if payload.get('secure') else target_scheme
            seed_url = f'{seed_scheme}://{cookie_host}/'

            try:
                if current_seed_url != seed_url:
                    driver.get(seed_url)
                    self._wait_for_page_ready(driver, timeout=self.PAGE_WAIT_SECONDS)
                    current_seed_url = seed_url

                cookie_payload = dict(payload)
                if not cookie_payload.get('domain'):
                    cookie_payload.pop('domain', None)

                driver.add_cookie(cookie_payload)
                applied += 1
            except (WebDriverException, AssertionError, ValueError, TypeError):
                continue

        if applied == 0:
            raise UploadConfigurationError(
                'No valid cookies could be applied. Re-export cookies and ensure domain matches target URL.'
            )

        driver.get(landing_url or self.config.target_url)
        self._wait_for_page_ready(driver)
        self._pause_between_steps()

    def _has_cookie_for_target_host(self, cookies: list[dict[str, Any]], target_host: str) -> bool:
        target = (target_host or '').strip().lower().lstrip('.')
        if not target:
            return False
        for cookie in cookies:
            domain = str(cookie.get('domain') or '').strip().lower().lstrip('.')
            if not domain:
                continue
            if target == domain or target.endswith(f'.{domain}') or domain.endswith(f'.{target}'):
                return True
        return False

    def _assert_logged_in(self, driver: webdriver.Firefox) -> None:
        if self.config.login_check_selector:
            try:
                WebDriverWait(driver, self.LOGIN_WAIT_SECONDS).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.config.login_check_selector))
                )
                return
            except TimeoutException as exc:
                raise UploadAuthExpiredError(
                    self._auth_expired_message(driver.current_url)
                ) from exc

        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(
                self._auth_expired_message(driver.current_url)
            )

    def _is_login_url(self, url: str) -> bool:
        lowered = (url or '').lower()
        return any(token in lowered for token in ['login', 'signin', 'auth'])

    def _auth_expired_message(self, current_url: str) -> str:
        base = 'Cookies seem expired or invalid. Please update cookies from admin panel.'
        host = (urlsplit(current_url).hostname or '').strip().lower()
        if not host:
            return base
        if self._has_auth_cookie_for_host(host):
            return base
        return (
            f'{base} No auth cookie was found for domain "{host}". '
            'Export cookies while logged in on that domain and save again.'
        )

    def _has_auth_cookie_for_host(self, host: str) -> bool:
        tracking_prefixes = ('_ga', '_gid', '_gcl', '_cl', '__stripe')
        try:
            cookies = self._parse_cookies(self.config.cookies_json)
        except UploadConfigurationError:
            return False

        for cookie in cookies:
            raw_domain = str(cookie.get('domain') or '').strip().lower().lstrip('.')
            if not raw_domain:
                continue
            if not (host == raw_domain or host.endswith(f'.{raw_domain}')):
                continue

            name = str(cookie.get('name') or '').strip().lower()
            if not name:
                continue
            if any(name.startswith(prefix) for prefix in tracking_prefixes):
                continue
            return True
        return False

    def _parse_cookies(self, raw: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UploadConfigurationError('Cookies JSON is invalid.') from exc
        if not isinstance(payload, list):
            raise UploadConfigurationError('Cookies JSON must be a list.')
        return [item for item in payload if isinstance(item, dict)]

    def _normalize_cookie(self, cookie: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in ('name', 'value', 'path', 'domain'):
            value = cookie.get(key)
            if value is not None:
                payload[key] = value

        raw_expiry = cookie.get('expiry', cookie.get('expirationDate'))
        if raw_expiry is not None:
            try:
                expiry = int(float(raw_expiry))
                if expiry > 0:
                    payload['expiry'] = expiry
            except (TypeError, ValueError):
                pass

        for bool_key in ('secure', 'httpOnly'):
            raw = cookie.get(bool_key)
            if raw is not None:
                payload[bool_key] = bool(raw)

        same_site_raw = cookie.get('sameSite')
        if isinstance(same_site_raw, str):
            normalized = same_site_raw.strip().lower()
            same_site_map = {
                'strict': 'Strict',
                'lax': 'Lax',
                'none': 'None',
                'no_restriction': 'None',
            }
            same_site_value = same_site_map.get(normalized)
            if same_site_value:
                payload['sameSite'] = same_site_value

        return payload

    def _create_driver(self) -> webdriver.Firefox:
        options = FirefoxOptions()
        options.add_argument('--headless')
        
        # Explicitly support non-snap firefox-esr on Ubuntu servers
        esr_path = Path('/usr/bin/firefox-esr')
        if esr_path.exists():
            options.binary_location = str(esr_path)
            
        options.set_capability('pageLoadStrategy', 'normal')
        service = (
            FirefoxService(executable_path=self.config.geckodriver_path)
            if self.config.geckodriver_path
            else FirefoxService()
        )
        try:
            driver = webdriver.Firefox(service=service, options=options)
            driver.set_page_load_timeout(self.PAGELOAD_TIMEOUT_SECONDS)
            return driver
        except WebDriverException as exc:
            raise UploadConfigurationError(
                'Failed to start Firefox WebDriver. Install Firefox + geckodriver and verify permissions.'
            ) from exc

    def _retain_debug_browser(self, driver: webdriver.Firefox) -> None:
        self.DEBUG_BROWSER_POOL.append(driver)
        while len(self.DEBUG_BROWSER_POOL) > self.DEBUG_BROWSER_POOL_LIMIT:
            stale = self.DEBUG_BROWSER_POOL.pop(0)
            try:
                stale.quit()
            except Exception:
                pass

    def _load_config(self) -> UploadAutomationConfig:
        rows = self.db.query(Setting).filter(Setting.key.in_(self.SETTINGS_KEYS)).all()
        values = {row.key: row.value for row in rows}

        target_url = (values.get('upload_target_url') or '').strip()
        if not target_url:
            raise UploadConfigurationError('upload_target_url is empty. Configure it in admin settings.')

        return UploadAutomationConfig(
            headless=_parse_bool(values.get('upload_firefox_headless'), default=False),
            target_url=target_url,
            cookies_json=values.get('upload_cookies_json') or '[]',
            search_input_selector=values.get('upload_search_input_selector') or "input[type='search']",
            course_result_xpath_template=values.get('upload_course_result_xpath_template')
            or "//a[contains(normalize-space(.), {query})]",
            sections_button_xpath=values.get('upload_sections_button_xpath')
            or "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'فصل') and contains(normalize-space(.), 'جلس')]",
            units_button_xpath=values.get('upload_units_button_xpath') or "//a[contains(@href, '/units/')]",
            login_check_selector=values.get('upload_login_check_selector') or '',
            episode_page_indicator_selector=values.get('upload_episode_page_indicator_selector') or '',
            geckodriver_path=(values.get('upload_firefox_geckodriver_path') or '').strip() or None,
        )
