import json
import subprocess
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