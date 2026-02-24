import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.cookies import load_scraper_cookies

ProgressCallback = Callable[[dict], None]
LogCallback = Callable[[str, dict], None]


@dataclass
class DownloadResult:
    path: Path
    total_size: int | None
    downloaded_bytes: int


class DownloadEngine:
    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.max_retries = settings.download_retry_attempts
        self.speed_limit_kb = settings.download_speed_limit_kb

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(settings.download_retry_attempts),
        wait=wait_exponential(multiplier=settings.download_retry_backoff_seconds, min=1, max=15),
        reraise=True,
    )
    def _head(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        prepared_headers = self._prepare_headers(url, headers)
        cookies = load_scraper_cookies()
        response = requests.head(url, headers=prepared_headers, cookies=cookies, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        return response

    def download(
        self,
        url: str,
        destination: Path,
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> DownloadResult:
        destination.parent.mkdir(parents=True, exist_ok=True)

        base_headers = self._prepare_headers(url, headers)
        head = self._head(url, headers=base_headers)
        total_size = int(head.headers.get('Content-Length', '0')) or None

        existing = destination.stat().st_size if destination.exists() else 0
        request_headers = dict(base_headers)

        if existing and total_size and existing < total_size:
            request_headers['Range'] = f'bytes={existing}-'
            mode = 'ab'
        else:
            existing = 0
            mode = 'wb'

        cookies = load_scraper_cookies()
        with requests.get(url, headers=request_headers, cookies=cookies, stream=True, timeout=self.timeout, allow_redirects=True) as response:
            if response.status_code not in (200, 206):
                response.raise_for_status()

            if mode == 'ab' and response.status_code == 200:
                existing = 0
                mode = 'wb'

            started_at = time.time()
            downloaded = existing
            last_log = started_at

            with destination.open(mode) as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded += len(chunk)

                    elapsed = max(time.time() - started_at, 0.001)
                    speed = downloaded / elapsed
                    eta = None
                    if total_size and speed > 0:
                        eta = (total_size - downloaded) / speed

                    if progress_callback:
                        percent = (downloaded / total_size * 100) if total_size else 0
                        progress_callback(
                            {
                                'downloaded': downloaded,
                                'total': total_size,
                                'percent': round(percent, 2),
                                'speed_bps': round(speed, 2),
                                'eta_seconds': round(eta, 2) if eta is not None else None,
                            }
                        )

                    now = time.time()
                    if log_callback and now - last_log >= 5:
                        log_callback(
                            'download_progress',
                            {
                                'downloaded': downloaded,
                                'total': total_size,
                                'speed_bps': speed,
                            },
                        )
                        last_log = now

                    if self.speed_limit_kb > 0:
                        limit_bps = self.speed_limit_kb * 1024
                        expected_elapsed = downloaded / max(limit_bps, 1)
                        if expected_elapsed > elapsed:
                            time.sleep(expected_elapsed - elapsed)

        return DownloadResult(path=destination, total_size=total_size, downloaded_bytes=downloaded)

    def _prepare_headers(self, url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = {
            'User-Agent': settings.scraper_user_agent,
            'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
            'Accept': '*/*',
            **(headers or {}),
        }
        host = (urlparse(url).hostname or '').lower()
        if host.endswith('git.ir') and 'Referer' not in merged:
            merged['Referer'] = 'https://git.ir/'
        return merged
