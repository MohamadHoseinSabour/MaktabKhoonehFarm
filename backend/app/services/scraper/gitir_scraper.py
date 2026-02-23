import re
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.services.scraper.base_scraper import BaseScraper, ScrapedCourseData
from app.services.scraper.utils import detect_platform_from_url, normalize_whitespace, parse_float, parse_int

logger = get_logger('scraper.gitir')

ACCESS_RESTRICTION_PATTERNS = [
    re.compile(r'محدودیت\s*دسترسی', re.IGNORECASE),
    re.compile(r'access\s*denied', re.IGNORECASE),
    re.compile(r'forbidden', re.IGNORECASE),
]


class GitIRScraper(BaseScraper):
    def __init__(self) -> None:
        self.headers = {
            'User-Agent': settings.scraper_user_agent,
            'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
        }

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch(self, url: str) -> str:
        with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text

    def scrape(self, url: str) -> ScrapedCourseData:
        html = self._fetch(url)
        soup = BeautifulSoup(html, 'lxml')

        raw_title = self._find_first_text(
            soup,
            [
                'h1.entry-title',
                'h1.post-title',
                'main h1',
                'article h1',
            ],
        )
        meta_title = self._meta_content(soup, ['og:title', 'twitter:title']) or (
            normalize_whitespace(soup.title.get_text(' ', strip=True)) if soup.title else None
        )
        title = raw_title
        access_limited = self._is_access_restricted(raw_title)
        if access_limited and meta_title:
            title = meta_title
        if not title:
            title = meta_title

        image_url = self._find_image_url(
            soup,
            [
                '.post-thumbnail img',
                '.entry-content img',
                'article img',
            ],
        )
        meta_image = self._meta_content(soup, ['og:image', 'twitter:image'])
        if not image_url and meta_image:
            image_url = urljoin(url, meta_image)

        raw_description = self._find_first_text(
            soup,
            [
                '.entry-content',
                '.post-content',
                'article .content',
            ],
        )
        meta_description = self._meta_content(soup, ['og:description', 'twitter:description', 'description'])
        description = raw_description
        if self._is_access_restricted(raw_description) and meta_description:
            description = meta_description
        if not description:
            description = meta_description

        metadata = self._extract_metadata(soup)
        metadata['access_limited'] = access_limited
        episodes = self._extract_curriculum(soup)

        title_en = title
        title_fa = None
        if title and re.search(r'[\u0600-\u06FF]', title):
            title_fa = title

        return ScrapedCourseData(
            title_en=title_en,
            title_fa=title_fa,
            description_en=description,
            thumbnail_url=image_url,
            instructor=metadata.get('instructor'),
            category=metadata.get('category'),
            tags=metadata.get('tags', []),
            duration=metadata.get('duration'),
            lectures_count=metadata.get('lectures_count'),
            level=metadata.get('level'),
            rating=metadata.get('rating'),
            students_count=metadata.get('students_count'),
            last_updated=metadata.get('last_updated'),
            language=metadata.get('language'),
            source_platform=detect_platform_from_url(url),
            extra_metadata=metadata,
            episodes=episodes,
        )

    def _find_first_text(self, soup: BeautifulSoup, selectors: list[str]) -> str | None:
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = normalize_whitespace(element.get_text(' ', strip=True))
                if text:
                    return text
        return None

    def _find_image_url(self, soup: BeautifulSoup, selectors: list[str]) -> str | None:
        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.get('src'):
                return element['src']
        return None

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        metadata: dict[str, Any] = {'tags': []}

        text_map = {}
        for li in soup.select('li, p, div'):
            text = normalize_whitespace(li.get_text(' ', strip=True))
            if ':' in text:
                key, value = text.split(':', 1)
                text_map[key.lower()] = value.strip()

        metadata['instructor'] = text_map.get('instructor') or text_map.get('teacher')
        metadata['duration'] = text_map.get('duration')
        metadata['level'] = text_map.get('level')
        metadata['language'] = text_map.get('language')
        metadata['category'] = text_map.get('category')
        metadata['last_updated'] = text_map.get('last updated')

        if lectures := text_map.get('lectures'):
            metadata['lectures_count'] = parse_int(lectures)

        if rating := text_map.get('rating'):
            metadata['rating'] = parse_float(rating)

        if students := text_map.get('students'):
            metadata['students_count'] = parse_int(students)

        tags: list[str] = []
        for node in soup.select('a[rel="tag"], .tags a'):
            tag_text = normalize_whitespace(node.get_text(' ', strip=True))
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
        metadata['tags'] = tags

        return metadata

    def _meta_content(self, soup: BeautifulSoup, names: list[str]) -> str | None:
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                text = normalize_whitespace(tag['content'])
                if text:
                    return text
        return None

    def _is_access_restricted(self, value: str | None) -> bool:
        if not value:
            return False
        for pattern in ACCESS_RESTRICTION_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def _extract_curriculum(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        episodes: list[dict[str, Any]] = []
        seen: set[str] = set()

        for node in soup.select('li, p, h3, h4'):
            text = normalize_whitespace(node.get_text(' ', strip=True))
            if not text:
                continue
            match = re.search(r'^(\d{1,3})[\s\-.]+(.+)$', text)
            if not match:
                continue
            number = int(match.group(1))
            title = match.group(2)
            key = f'{number}:{title.lower()}'
            if key in seen:
                continue
            seen.add(key)
            episodes.append({'episode_number': number, 'title_en': title})

        episodes.sort(key=lambda item: item['episode_number'])
        return episodes
