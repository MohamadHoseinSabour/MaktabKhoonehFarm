import requests

from app.services.downloader.link_expiry import (
    EXPIRED_LINK_ERROR_MESSAGE,
    build_download_error_message,
    clear_course_links_expired,
    is_expired_link_error,
    mark_course_links_expired,
)


class DummyCourse:
    def __init__(self):
        self.extra_metadata = {}


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response.url = 'https://git.ir/api/post/get-download-links/271xv/?token=t&hash=h&filename=001.mp4'
    return requests.HTTPError(f'{status_code} Client Error', response=response)


def test_is_expired_link_error_detects_tokenized_403():
    exc = _http_error(403)
    url = 'https://git.ir/api/post/get-download-links/271xv/?token=t&hash=h&filename=001.mp4'
    assert is_expired_link_error(exc, url) is True


def test_is_expired_link_error_ignores_non_tokenized_403():
    exc = _http_error(403)
    url = 'https://cdn.example.com/video.mp4'
    assert is_expired_link_error(exc, url) is False


def test_build_download_error_message_uses_expired_marker():
    exc = _http_error(410)
    url = 'https://git.ir/api/post/get-download-links/271xv/?token=t&hash=h&filename=001.mp4'
    assert build_download_error_message('Video', exc, url) == EXPIRED_LINK_ERROR_MESSAGE


def test_mark_and_clear_course_links_expired():
    course = DummyCourse()

    changed = mark_course_links_expired(course)
    assert changed is True
    assert course.extra_metadata.get('links_expired') is True
    assert 'links_expired_at' in course.extra_metadata

    changed = clear_course_links_expired(course)
    assert changed is True
    assert 'links_expired' not in course.extra_metadata
    assert 'links_expired_at' not in course.extra_metadata
