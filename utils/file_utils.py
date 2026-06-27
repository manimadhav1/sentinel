from __future__ import annotations
import shutil
import uuid
from pathlib import Path
from config import UPLOADS_DIR, SUPPORTED_EXTENSIONS


def detect_file_type(file_path: str | Path) -> str:
    suffix = Path(file_path).suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".xlsx": "excel", ".xls": "excel",
        ".csv": "csv",
        ".png": "image", ".jpg": "image",
        ".jpeg": "image", ".webp": "image",
    }
    return mapping.get(suffix, "unknown")


def is_supported(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def save_upload(file_bytes: bytes, original_filename: str) -> Path:
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / unique_name
    dest.write_bytes(file_bytes)
    return dest


def safe_delete(file_path: str | Path) -> None:
    p = Path(file_path)
    if p.exists():
        p.unlink()


def copy_to_output(src: Path, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(src, dest)
    return dest
