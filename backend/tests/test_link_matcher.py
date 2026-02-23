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


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self.rows)


class _FakeDB:
    def __init__(self):
        self.episodes = []

    def query(self, _model):
        return _FakeQuery(self.episodes)

    def add(self, episode):
        self.episodes.append(episode)

    def commit(self):
        return None


def test_link_matcher_creates_single_episode_for_video_and_subtitle():
    db = _FakeDB()
    matcher = LinkMatcher(db=db)
    course_id = uuid.uuid4()

    video = parse_link('https://git.ir/api/post/get-download-links/271xv/?token=t&hash=h&filename=001-Intro-abcd-git.ir.mp4')
    subtitle = parse_link('https://git.ir/api/post/get-download-links/271xv/?token=t&hash=h&filename=001-Intro-abcd-git.ir.fa.srt')

    result = matcher.apply(course_id=course_id, links=[video, subtitle], apply_changes=True)

    assert result.created == 1
    assert result.matched == 1
    assert len(db.episodes) == 1
    assert db.episodes[0].video_download_url is not None
    assert db.episodes[0].subtitle_download_url is not None
