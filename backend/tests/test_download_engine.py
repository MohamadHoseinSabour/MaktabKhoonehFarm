from app.services.downloader.engine import DownloadEngine


def test_prepare_headers_sets_user_agent_and_referer_for_git_ir():
    engine = DownloadEngine()
    headers = engine._prepare_headers('https://git.ir/api/post/get-download-links/x/?token=a')

    assert headers.get('User-Agent')
    assert headers.get('Referer') == 'https://git.ir/'


def test_prepare_headers_keeps_custom_headers():
    engine = DownloadEngine()
    headers = engine._prepare_headers('https://example.com/file.mp4', {'User-Agent': 'CustomAgent/1.0'})

    assert headers['User-Agent'] == 'CustomAgent/1.0'
    assert 'Referer' not in headers