from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import PROJECT_ROOT


class VideoWatermarkProcessor:
    def __init__(
        self,
        cover_path: Path | None = None,
        seconds_to_apply: int = 30,
        base_width: int = 1920,
        base_height: int = 1080,
    ) -> None:
        assets_root = PROJECT_ROOT / 'assets'
        self.cover_path = cover_path or (assets_root / 'logo-cover.png')
        self.seconds_to_apply = seconds_to_apply
        self.base_width = base_width
        self.base_height = base_height

    def process(self, video_path: Path) -> dict:
        if not video_path.exists():
            return {'checked': False, 'covered': False, 'reason': 'video_missing'}
        if not self.cover_path.exists():
            return {'checked': False, 'covered': False, 'reason': 'asset_missing'}
        ffmpeg_path = shutil.which('ffmpeg')
        ffprobe_path = shutil.which('ffprobe')
        if ffmpeg_path is None or ffprobe_path is None:
            return {'checked': False, 'covered': False, 'reason': 'ffmpeg_missing'}

        video_size = self._probe_size(video_path, ffprobe_path)
        cover_size = self._probe_size(self.cover_path, ffprobe_path)
        if not video_size or not cover_size:
            return {'checked': False, 'covered': False, 'reason': 'probe_failed'}

        scaled_cover = self._scaled_cover_size(video_size, cover_size)
        if not scaled_cover:
            return {'checked': False, 'covered': False, 'reason': 'invalid_scale'}

        applied = self._apply_cover(video_path, self.seconds_to_apply, scaled_cover[0], scaled_cover[1], ffmpeg_path)
        return {
            'checked': True,
            'covered': applied,
            'video_size': {'width': video_size[0], 'height': video_size[1]},
            'cover_size': {'width': scaled_cover[0], 'height': scaled_cover[1]},
        }

    def _probe_size(self, image_path: Path, ffprobe_path: str = 'ffprobe') -> tuple[int, int] | None:
        cmd = [
            ffprobe_path,
            '-v',
            'error',
            '-select_streams',
            'v:0',
            '-show_entries',
            'stream=width,height',
            '-of',
            'csv=s=x:p=0',
            str(image_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return None
        text = (result.stdout or '').strip()
        if 'x' not in text:
            return None
        w_text, h_text = text.split('x', 1)
        try:
            return int(w_text), int(h_text)
        except ValueError:
            return None

    def _scaled_cover_size(self, video_size: tuple[int, int], cover_size: tuple[int, int]) -> tuple[int, int] | None:
        video_w, video_h = video_size
        cover_w, cover_h = cover_size
        if video_w <= 0 or video_h <= 0 or cover_w <= 0 or cover_h <= 0:
            return None

        scale_x = video_w / self.base_width
        scale_y = video_h / self.base_height
        if scale_x <= 0 or scale_y <= 0:
            return None

        target_w = max(1, int(round(cover_w * scale_x)))
        target_h = max(1, int(round(cover_h * scale_y)))
        return target_w, target_h

    def _apply_cover(self, video_path: Path, seconds: int, cover_w: int, cover_h: int, ffmpeg_path: str = 'ffmpeg') -> bool:
        tmp_path = video_path.with_name(f'{video_path.stem}.tmp{video_path.suffix}')
        filter_graph = (
            f"[1:v]scale={cover_w}:{cover_h}:flags=lanczos,format=rgba[logo];"
            f"[0:v][logo]overlay=0:0:enable='between(t,0,{seconds})'[v]"
        )
        cmd = [
            ffmpeg_path,
            '-y',
            '-i',
            str(video_path),
            '-i',
            str(self.cover_path),
            '-filter_complex',
            filter_graph,
            '-map',
            '[v]',
            '-map',
            '0:a?',
            '-c:v',
            'libx264',
            '-preset',
            'veryfast',
            '-crf',
            '19',
            '-c:a',
            'copy',
            '-movflags',
            '+faststart',
            str(tmp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not tmp_path.exists():
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False
        tmp_path.replace(video_path)
        return True
