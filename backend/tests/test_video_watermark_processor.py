from pathlib import Path

from app.services.processor.video_watermark_processor import VideoWatermarkProcessor


def test_scaled_cover_size_uses_video_ratio_against_base_frame():
    processor = VideoWatermarkProcessor(base_width=1920, base_height=1080)

    # 960x540 is exactly half of 1920x1080, so cover should be scaled by 0.5 on both axes.
    scaled = processor._scaled_cover_size((960, 540), (400, 200))

    assert scaled == (200, 100)


def test_apply_cover_uses_temp_file_with_video_extension(monkeypatch, tmp_path: Path):
    cover = tmp_path / 'cover.png'
    video = tmp_path / 'clip.mp4'
    cover.write_bytes(b'cover')
    video.write_bytes(b'video')
    processor = VideoWatermarkProcessor(cover_path=cover)

    captured = {}

    def fake_run(cmd, capture_output, text, check):
        captured['cmd'] = cmd
        tmp_out = Path(cmd[-1])
        tmp_out.write_bytes(b'watermarked')

        class Result:
            returncode = 0
            stdout = ''
            stderr = ''

        return Result()

    monkeypatch.setattr('subprocess.run', fake_run)

    ok = processor._apply_cover(video, 30, 100, 50, ffmpeg_path='ffmpeg')

    assert ok is True
    assert Path(captured['cmd'][-1]).name.endswith('.mp4')
    assert video.read_bytes() == b'watermarked'
