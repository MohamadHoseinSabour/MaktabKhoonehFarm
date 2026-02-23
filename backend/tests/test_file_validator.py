from pathlib import Path

from app.services.downloader.file_validator import FileValidator


def test_validate_video_falls_back_when_ffprobe_missing(monkeypatch, tmp_path: Path):
    sample = tmp_path / 'video.mp4'
    sample.write_bytes(b'0' * 2048)

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError('ffprobe missing')

    monkeypatch.setattr('subprocess.run', _raise)
    assert FileValidator.validate_video(sample) is True