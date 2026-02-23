import hashlib
import subprocess
from pathlib import Path

import srt


class FileValidator:
    @staticmethod
    def validate_size(file_path: Path, expected_size: int | None) -> bool:
        if expected_size is None:
            return True
        return file_path.exists() and file_path.stat().st_size == expected_size

    @staticmethod
    def validate_video(file_path: Path) -> bool:
        if not file_path.exists() or file_path.stat().st_size == 0:
            return False
        cmd = [
            'ffprobe',
            '-v',
            'error',
            '-show_format',
            '-show_streams',
            str(file_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return result.returncode == 0
        except FileNotFoundError:
            # Local development fallback when ffprobe is not installed.
            return file_path.exists() and file_path.stat().st_size > 1024

    @staticmethod
    def validate_srt(file_path: Path) -> bool:
        if not file_path.exists() or file_path.stat().st_size == 0:
            return False
        try:
            payload = file_path.read_text(encoding='utf-8', errors='ignore')
            list(srt.parse(payload))
            return True
        except Exception:
            return False

    @staticmethod
    def calculate_hash(file_path: Path, algorithm: str = 'sha256') -> str:
        hasher = hashlib.new(algorithm)
        with file_path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()
