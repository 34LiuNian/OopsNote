"""Local file storage utilities for assets."""

from __future__ import annotations

import base64
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .models import AssetMetadata, AssetSource

DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")


class LocalAssetStore:
    """Persists uploaded assets onto disk and tracks metadata in-memory."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = (
            base_dir or Path(__file__).resolve().parent.parent / "storage" / "assets"
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_base64(
        self,
        data: str,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> AssetMetadata:
        """Persist a base64 payload and return its metadata."""
        payload, resolved_mime = self._extract_payload(data, mime_type)
        asset_id = uuid4().hex
        extension = self._determine_extension(filename, resolved_mime)
        final_name = filename or f"{asset_id}{extension}"
        safe_name = final_name.replace("/", "_")
        path = self.base_dir / safe_name
        binary = base64.b64decode(payload)
        path.write_bytes(binary)
        return AssetMetadata(
            asset_id=asset_id,
            source=AssetSource.UPLOAD,
            original_reference="upload",
            path=str(path),
            mime_type=resolved_mime,
            size_bytes=len(binary),
            created_at=datetime.now(timezone.utc),
        )

    def register_remote(
        self, url: str, mime_type: Optional[str] = None
    ) -> AssetMetadata:
        """Register a remote asset without downloading it."""
        return AssetMetadata(
            asset_id=uuid4().hex,
            source=AssetSource.REMOTE,
            original_reference=url,
            path=None,
            mime_type=mime_type,
            size_bytes=None,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _extract_payload(
        data: str, fallback_mime: Optional[str]
    ) -> tuple[str, Optional[str]]:
        match = DATA_URI_RE.match(data)
        if match:
            return match.group("data"), match.group("mime")
        return data, fallback_mime

    @staticmethod
    def _determine_extension(filename: Optional[str], mime_type: Optional[str]) -> str:
        if filename and Path(filename).suffix:
            return Path(filename).suffix
        if mime_type:
            guessed = mimetypes.guess_extension(mime_type)
            if guessed:
                return guessed
        return ".bin"
