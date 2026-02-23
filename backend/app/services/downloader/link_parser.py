import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class ParsedLink:
    url: str
    filename: str
    decoded_filename: str
    episode_number: int | None
    episode_title: str | None
    hash_code: str | None
    file_type: str
    subtitle_language: str | None
    token: str | None
    hash: str | None
    course_api_id: str | None


FILE_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
EPISODE_RE = re.compile(r'^(?P<num>\d{3})[-_\s]+(?P<title>.+)$')
HASH_CODE_RE = re.compile(r'-(?P<hash>[A-Za-z0-9]{4})-git\.ir', re.IGNORECASE)


def parse_bulk_links(raw_links: str) -> list[ParsedLink]:
    normalized = raw_links.replace('&amp;', '&')
    links = FILE_URL_RE.findall(normalized)
    parsed: list[ParsedLink] = []
    for link in links:
        item = parse_link(link)
        if item:
            parsed.append(item)
    return parsed


def parse_link(link: str) -> ParsedLink | None:
    parsed_url = urlparse(link)
    query = parse_qs(parsed_url.query.replace('amp;', ''))

    filename_query = _first_value(query, 'filename', 'file', 'name')
    filename = Path(unquote(filename_query)).name if filename_query else Path(unquote(parsed_url.path)).name
    if not filename:
        return None

    decoded_filename = unquote(filename)
    file_type, subtitle_language = detect_file_type(decoded_filename)
    episode_number, episode_title = extract_episode_info(decoded_filename)

    hash_match = HASH_CODE_RE.search(decoded_filename)
    hash_code = hash_match.group('hash') if hash_match else None

    token = _first_value(query, 'token', 't')
    hash_value = _first_value(query, 'hash', 'h')
    course_api_id = extract_course_api_id(parsed_url.path, query)

    return ParsedLink(
        url=link,
        filename=filename,
        decoded_filename=decoded_filename,
        episode_number=episode_number,
        episode_title=episode_title,
        hash_code=hash_code,
        file_type=file_type,
        subtitle_language=subtitle_language,
        token=token,
        hash=hash_value,
        course_api_id=course_api_id,
    )


def detect_file_type(filename: str) -> tuple[str, str | None]:
    lower = filename.lower()

    if lower.endswith('.fa.srt'):
        return 'subtitle', 'fa'
    if lower.endswith('.en.srt'):
        return 'subtitle', 'en'
    if lower.endswith('.srt'):
        return 'subtitle', None
    if lower.endswith(('.zip', '.rar', '.7z', '.pdf')):
        return 'exercise', None
    if lower.endswith(('.mp4', '.mkv', '.avi', '.mov')):
        return 'video', None

    return 'unknown', None


def extract_episode_info(filename: str) -> tuple[int | None, str | None]:
    stem = filename
    for suffix in ['.fa.srt', '.en.srt', '.srt', '.mp4', '.mkv', '.avi', '.mov', '.zip', '.rar', '.7z', '.pdf']:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    stem = re.sub(r'-[A-Za-z0-9]{4}-git\.ir$', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'-git\.ir$', '', stem, flags=re.IGNORECASE)

    match = EPISODE_RE.match(stem)
    if not match:
        return None, None

    number = int(match.group('num'))
    title = match.group('title').replace('-', ' ').replace('_', ' ').strip()
    return number, title


def extract_course_api_id(path: str, query: dict[str, list[str]]) -> str | None:
    for key in ('course_id', 'id'):
        value = _first_value(query, key)
        if value:
            return value

    direct_match = re.search(r'/get-download-links/([a-z0-9]{4,10})/?', path, flags=re.IGNORECASE)
    if direct_match:
        return direct_match.group(1)

    segments = [seg for seg in path.split('/') if seg]
    for segment in reversed(segments):
        if re.match(r'^[a-z0-9]{4,10}$', segment, flags=re.IGNORECASE):
            return segment
    return None


def _first_value(query: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        values = query.get(key)
        if values:
            return values[0]
    return None
