from app.services.downloader.link_parser import parse_bulk_links


def test_parse_bulk_links_extracts_episode_metadata():
    raw = '''
    https://example.com/271xv/001-Introduction-m1YH-git.ir.mp4?token=abc123&hash=h1
    https://example.com/271xv/001-Introduction-m1YH-git.ir.fa.srt?token=abc123&hash=h1
    '''

    parsed = parse_bulk_links(raw)
    assert len(parsed) == 2

    video = parsed[0]
    subtitle = parsed[1]

    assert video.course_api_id == '271xv'
    assert video.episode_number == 1
    assert video.episode_title == 'Introduction'
    assert video.hash_code == 'm1YH'
    assert video.file_type == 'video'

    assert subtitle.file_type == 'subtitle'
    assert subtitle.subtitle_language == 'fa'
    assert subtitle.token == 'abc123'
    assert subtitle.hash == 'h1'