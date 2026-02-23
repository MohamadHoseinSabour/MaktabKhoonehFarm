import re
from urllib.parse import urlparse


PLATFORM_PATTERNS = {
    'udemy': re.compile(r'(^|-)udemy(-|$)', re.IGNORECASE),
    'coursera': re.compile(r'(^|-)coursera(-|$)', re.IGNORECASE),
    'lynda': re.compile(r'(^|-)lynda(-|$)', re.IGNORECASE),
    'linkedin-learning': re.compile(r'(^|-)linkedin(-|$)', re.IGNORECASE),
    'pluralsight': re.compile(r'(^|-)pluralsight(-|$)', re.IGNORECASE),
}


def detect_platform_from_url(url: str) -> str | None:
    slug = urlparse(url).path.lower().strip('/').replace('_', '-')
    for name, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(slug):
            return name.replace('-', ' ').title()
    return None


def normalize_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def parse_int(value: str) -> int | None:
    only_digits = re.sub(r'[^0-9]', '', value)
    if not only_digits:
        return None
    try:
        return int(only_digits)
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    normalized = re.sub(r'[^0-9.]', '', value)
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None