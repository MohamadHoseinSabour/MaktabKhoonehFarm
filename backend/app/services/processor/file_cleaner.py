import re
from pathlib import Path


def clean_filename(filename: str) -> str:
    """Normalize filename by removing git.ir markers and random hash codes."""
    base, *suffixes = filename.split('.')
    base = re.sub(r'-[A-Za-z0-9]{4}-git\.ir$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'-git\.ir$', '', base, flags=re.IGNORECASE)
    base = base.replace('_', '-').strip('-')
    extension = '.'.join(suffixes)
    return f'{base}.{extension}' if extension else base


def build_episode_filename(number: int, title: str, extension: str) -> str:
    safe_title = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF\s-]', '', title).strip().replace(' ', '-')
    return f'{number:03d}-{safe_title}.{extension.lstrip(".")}'


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)