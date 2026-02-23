from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScrapedCourseData:
    title_en: str | None = None
    title_fa: str | None = None
    description_en: str | None = None
    description_fa: str | None = None
    instructor: str | None = None
    thumbnail_url: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    duration: str | None = None
    lectures_count: int | None = None
    level: str | None = None
    rating: float | None = None
    students_count: int | None = None
    last_updated: str | None = None
    language: str | None = None
    source_platform: str | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    episodes: list[dict[str, Any]] = field(default_factory=list)


class BaseScraper:
    def scrape(self, url: str) -> ScrapedCourseData:
        raise NotImplementedError