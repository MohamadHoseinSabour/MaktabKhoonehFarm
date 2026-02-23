import uuid

from app.models.episode import Episode
from app.services.downloader.link_matcher import LinkMatcher
from app.services.downloader.link_parser import parse_link


def test_link_matcher_prefers_exact_filename_match():
    matcher = LinkMatcher(db=None)

    ep = Episode(id=uuid.uuid4(), course_id=uuid.uuid4(), episode_number=1, title_en='Introduction', video_filename='001-Introduction-m1YH-git.ir.mp4', sort_order=1)
    other = Episode(id=uuid.uuid4(), course_id=uuid.uuid4(), episode_number=2, title_en='Setup', video_filename='002-Setup-abcd-git.ir.mp4', sort_order=2)

    link = parse_link('https://example.com/x/001-Introduction-m1YH-git.ir.mp4?token=t')
    assert link is not None

    matched = matcher._match_episode(link, [ep, other], {1: ep, 2: other}, {ep.video_filename.lower(): ep, other.video_filename.lower(): other})
    assert matched == ep