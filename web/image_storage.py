"""On-disk storage for Animal Photos and Enclosure Photos (see CONTEXT.md: Animal Photo, Enclosure
Photo) — one image per Animal/Enclosure, stored under data/images/<kind>/<id>.<ext>, replacing
whatever was there before on a new upload (never a history/gallery). web/admin_queries.py pairs
this with the owning row's own image_filename column; this module only ever touches the filesystem.

data/images/ is backed up and restored alongside data/husbandrytracker.db (see ingest/ingest.py's
_perform_backup, tray/supervisor.py's _restore_backup) so a photo survives a Restore the same way
every other durable piece of state does — see CONTEXT.md: Backup.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_paths import APP_ROOT

IMAGES_DIR = APP_ROOT / "data" / "images"

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB

# Content-type -> stored extension. Deliberately narrow (see grill-me decision) rather than
# trusting a client-supplied filename extension, which could be forged or absent.
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _kind_dir(kind: str) -> Path:
    return IMAGES_DIR / kind


def _existing_path(kind: str, entity_id: int) -> Path | None:
    """Finds the current file for this entity regardless of its extension — a replacement upload
    can arrive in a different format than what's already stored (e.g. a PNG replacing a JPEG)."""
    directory = _kind_dir(kind)
    if not directory.is_dir():
        return None
    matches = list(directory.glob(f"{entity_id}.*"))
    return matches[0] if matches else None


def save_image(kind: str, entity_id: int, content_type: str | None, data: bytes) -> str:
    """Validates and writes `data` to data/images/<kind>/<entity_id>.<ext>, deleting whatever was
    stored for this entity before (one image per Animal/Enclosure — see CONTEXT.md). Returns the
    new filename (e.g. "14.jpg", not the full path) to store on the owning row. Raises ValueError
    with a friendly message on an unsupported type or an oversized upload."""
    ext = _ALLOWED_CONTENT_TYPES.get(content_type or "")
    if ext is None:
        raise ValueError("Only JPEG, PNG, or WebP images are accepted.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image is too large — max {MAX_IMAGE_BYTES // (1024 * 1024)}MB.")
    if not data:
        raise ValueError("No image file was uploaded.")
    remove_image(kind, entity_id)
    directory = _kind_dir(kind)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{entity_id}.{ext}"
    (directory / filename).write_bytes(data)
    return filename


def remove_image(kind: str, entity_id: int) -> None:
    existing = _existing_path(kind, entity_id)
    if existing is not None:
        existing.unlink(missing_ok=True)
