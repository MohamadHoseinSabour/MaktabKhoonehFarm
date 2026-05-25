import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def extract_video_metadata(path: Path) -> dict:
    command = [
        'ffprobe',
        '-v',
        'error',
        '-print_format',
        'json',
        '-show_streams',
        '-show_format',
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr.strip()}

    data = json.loads(result.stdout or '{}')
    streams = data.get('streams', [])
    video_stream = next((stream for stream in streams if stream.get('codec_type') == 'video'), {})

    return {
        'ok': True,
        'duration': data.get('format', {}).get('duration'),
        'size': data.get('format', {}).get('size'),
        'bit_rate': data.get('format', {}).get('bit_rate'),
        'resolution': f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
        'codec': video_stream.get('codec_name'),
    }


def probe_duration_seconds(metadata: dict | None) -> float | None:
    if not isinstance(metadata, dict):
        return None
    raw_duration = metadata.get('duration')
    if raw_duration in (None, ''):
        return None
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def remux_mp4_for_upload(path: Path) -> dict:
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        return {'ok': False, 'error': 'ffmpeg_missing'}

    fd, temp_name = tempfile.mkstemp(prefix=f'{path.stem}.upload-', suffix=path.suffix or '.mp4', dir=path.parent)
    os.close(fd)
    temp_path = Path(temp_name)

    command = [
        ffmpeg_path,
        '-y',
        '-i',
        str(path),
        '-map',
        '0:v:0',
        '-map',
        '0:a?',
        '-map_metadata',
        '0',
        '-sn',
        '-dn',
        '-c',
        'copy',
        '-movflags',
        '+faststart',
        str(temp_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not temp_path.exists():
        temp_path.unlink(missing_ok=True)
        return {'ok': False, 'error': result.stderr.strip() or 'ffmpeg_remux_failed'}

    metadata = extract_video_metadata(temp_path)
    if not metadata.get('ok'):
        temp_path.unlink(missing_ok=True)
        return {'ok': False, 'error': metadata.get('error') or 'ffprobe_after_remux_failed'}

    return {'ok': True, 'path': str(temp_path), 'metadata': metadata}
