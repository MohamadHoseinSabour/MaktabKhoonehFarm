import re
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.cookies import load_scraper_cookies
from app.core.logging import get_logger
from app.services.scraper.base_scraper import BaseScraper, ScrapedCourseData
from app.services.scraper.utils import detect_platform_from_url, normalize_whitespace, parse_float, parse_int

logger = get_logger('scraper.gitir')

ACCESS_RESTRICTION_PATTERNS = [
    re.compile(r'محدودیت\s*دسترسی', re.IGNORECASE),
    re.compile(r'access\s*denied', re.IGNORECASE),
    re.compile(r'forbidden', re.IGNORECASE),
]
PERSIAN_CHAR_RE = re.compile(r'[\u0600-\u06FF]')
LATIN_CHAR_RE = re.compile(r'[A-Za-z]')


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
        cookies = load_scraper_cookies()
        with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True, cookies=cookies) as client:
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
        if image_url:
            image_url = urljoin(url, image_url)
        meta_image = self._meta_content(soup, ['og:image', 'twitter:image'])
        if not image_url and meta_image:
            image_url = urljoin(url, meta_image)

        description_node = self._find_first_node(
            soup,
            ['.entry-content', '.post-content', 'article .content'],
        )
        raw_description = normalize_whitespace(description_node.get_text(' ', strip=True)) if description_node else None
        meta_description = self._meta_content(soup, ['og:description', 'twitter:description', 'description'])
        description_en, description_fa = self._extract_bilingual_descriptions(
            description_node,
            raw_description,
            meta_description,
        )

        if self._is_access_restricted(raw_description) and meta_description:
            description_en = meta_description
            description_fa = meta_description if self._contains_persian(meta_description) else description_fa

        metadata = self._extract_metadata(soup)
        metadata['access_limited'] = access_limited
        episodes = self._extract_curriculum(soup)

        title_en = title
        title_fa = None
        if title and self._contains_persian(title):
            title_fa = title
            if meta_title and not self._contains_persian(meta_title):
                title_en = meta_title
        elif meta_title and self._contains_persian(meta_title):
            title_fa = meta_title

        return ScrapedCourseData(
            title_en=title_en,
            title_fa=title_fa,
            description_en=description_en,
            description_fa=description_fa,
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

    def _find_first_node(self, soup: BeautifulSoup, selectors: list[str]):
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element
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

    def _contains_persian(self, value: str | None) -> bool:
        if not value:
            return False
        return bool(PERSIAN_CHAR_RE.search(value))

    def _extract_bilingual_descriptions(
        self,
        description_node,
        raw_description: str | None,
        meta_description: str | None,
    ) -> tuple[str | None, str | None]:
        blocks: list[str] = []
        if description_node:
            for node in description_node.select('p, li'):
                text = normalize_whitespace(node.get_text(' ', strip=True))
                if len(text) >= 40:
                    blocks.append(text)

        if not blocks and raw_description:
            blocks = [raw_description]

        unique_blocks: list[str] = []
        seen: set[str] = set()
        for block in blocks:
            key = block.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_blocks.append(block)

        fa_blocks: list[str] = []
        en_blocks: list[str] = []
        for block in unique_blocks:
            persian_count = len(PERSIAN_CHAR_RE.findall(block))
            latin_count = len(LATIN_CHAR_RE.findall(block))
            if persian_count > 0 and persian_count >= latin_count:
                fa_blocks.append(block)
            if latin_count > 0 and latin_count >= persian_count:
                en_blocks.append(block)

        description_en = normalize_whitespace(' '.join(en_blocks[:6])) if en_blocks else None
        description_fa = normalize_whitespace(' '.join(fa_blocks[:6])) if fa_blocks else None

        if not description_en:
            description_en = meta_description or raw_description
        if not description_fa and raw_description and self._contains_persian(raw_description):
            description_fa = raw_description

        return description_en, description_fa

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
