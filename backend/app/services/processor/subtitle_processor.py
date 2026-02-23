from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
import re

import chardet
import srt


@dataclass
class SubtitleProcessingConfig:
    remove_ads: bool = True
    ad_patterns: list[str] = field(
        default_factory=lambda: [
            r'git\.ir',
            r'downloaded\s+from',
            r'translat(or|ed)\s+by',
        ]
    )
    normalize_persian_chars: bool = True
    remove_html_tags: bool = True
    renumber_entries: bool = True
    fix_overlap: bool = True


class SubtitleProcessor:
    def __init__(self, config: SubtitleProcessingConfig | None = None) -> None:
        self.config = config or SubtitleProcessingConfig()

    def process(self, source_path: Path, destination_path: Path) -> dict:
        payload = source_path.read_bytes()
        encoding = self._detect_encoding(payload)
        text = payload.decode(encoding, errors='replace')

        subtitles = list(srt.parse(text))
        cleaned = self._clean_subtitles(subtitles)

        if self.config.fix_overlap:
            self._fix_overlaps(cleaned)

        if self.config.renumber_entries:
            for index, item in enumerate(cleaned, start=1):
                item.index = index

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(srt.compose(cleaned), encoding='utf-8')

        return {
            'input_encoding': encoding,
            'input_count': len(subtitles),
            'output_count': len(cleaned),
        }

    def _detect_encoding(self, payload: bytes) -> str:
        guess = chardet.detect(payload)
        return guess.get('encoding') or 'utf-8'

    def _clean_subtitles(self, subtitles: list[srt.Subtitle]) -> list[srt.Subtitle]:
        result: list[srt.Subtitle] = []
        for sub in subtitles:
            content = sub.content.strip()

            if self.config.remove_html_tags:
                content = re.sub(r'<[^>]+>', '', content)

            if self.config.normalize_persian_chars:
                content = (
                    content.replace('\u064A', '\u06CC')
                    .replace('\u0643', '\u06A9')
                    .replace('\u200c\u200c', '\u200c')
                )

            if self.config.remove_ads and self._is_advertisement(content):
                continue

            if not content:
                continue

            sub.content = content
            result.append(sub)

        return result

    def _is_advertisement(self, line: str) -> bool:
        lower = line.lower()
        for pattern in self.config.ad_patterns:
            if re.search(pattern, lower):
                return True
        return False

    def _fix_overlaps(self, subtitles: list[srt.Subtitle]) -> None:
        for index in range(len(subtitles) - 1):
            current = subtitles[index]
            next_item = subtitles[index + 1]
            if current.end > next_item.start:
                adjusted = next_item.start - timedelta(milliseconds=1)
                if adjusted > current.start:
                    current.end = adjusted
