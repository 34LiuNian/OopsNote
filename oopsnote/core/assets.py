"""资产文件存储。

图片 / PDF 以文件形式落盘，元数据记录相对路径。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PIL import Image, UnidentifiedImageError


DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")
MAX_UPLOAD_IMAGE_BYTES = 16 * 1024 * 1024
MAX_UPLOAD_IMAGE_PIXELS = 80_000_000
_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}


class AssetStore:
    """本地资产文件存储。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[1] / "storage" / "assets"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_base64(self, data: str, filename: Optional[str] = None) -> str:
        """保存 base64 字符串，返回相对路径。"""
        payload, mime = self._extract(data)
        ext = self._guess_ext(filename, mime)
        name = f"{uuid4().hex}{ext}"
        decoded = self._decode_base64(payload)
        self._write_atomic(self.base_dir / name, decoded)
        return f"/assets/{name}"

    def save_uploaded_image(
        self,
        data: str,
        filename: Optional[str] = None,
        *,
        max_bytes: int = MAX_UPLOAD_IMAGE_BYTES,
        max_pixels: int = MAX_UPLOAD_IMAGE_PIXELS,
    ) -> tuple[str, str]:
        """Validate and persist an uploaded raster image under a unique name."""
        payload, _declared_mime = self._extract(data)
        decoded = self._decode_base64(payload, max_bytes=max_bytes)
        try:
            with Image.open(BytesIO(decoded)) as image:
                image_format = str(image.format or "").upper()
                dimensions = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise ValueError("Uploaded asset is not a valid supported image") from error
        if image_format not in _IMAGE_FORMATS:
            raise ValueError("Uploaded image type is not supported")
        width, height = dimensions
        if width <= 0 or height <= 0 or width * height > max_pixels:
            raise ValueError(f"Uploaded image exceeds {max_pixels} pixels")
        extension, mime_type = _IMAGE_FORMATS[image_format]
        # The original name remains metadata only. Storage identity must never be
        # derived from a client-controlled or commonly repeated filename.
        del filename
        name = f"{uuid4().hex}{extension}"
        self._write_atomic(self.base_dir / name, decoded)
        return f"/assets/{name}", mime_type

    def save_file(self, source_path: str | Path) -> str:
        """复制文件到资产目录，返回相对路径。"""
        source = Path(source_path)
        asset_id = uuid4().hex
        ext = source.suffix or ".bin"
        name = f"{asset_id}{ext}"
        dest = self.base_dir / name
        self._write_atomic(dest, source.read_bytes())
        return f"/assets/{name}"

    def save_bytes(self, data: bytes, filename: str, stable_name: Optional[str] = None) -> str:
        """保存原始上传文件；stable_name 用于内容哈希去重。"""
        ext = Path(filename).suffix or ".bin"
        name = f"{stable_name}{ext}" if stable_name else f"{uuid4().hex}{ext}"
        safe_name = name.replace("/", "_").replace("\\", "_")
        path = self.base_dir / safe_name
        if not path.exists() or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(data).digest():
            self._write_atomic(path, data)
        return f"/assets/{safe_name}"

    def resolve(self, asset_path: str) -> Path:
        """Resolve one managed asset path without allowing directory traversal."""
        relative = asset_path.removeprefix("/assets/")
        candidate = (self.base_dir / relative).resolve()
        base = self.base_dir.resolve()
        if candidate.parent != base:
            raise ValueError("Asset path is outside the managed asset directory")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    @staticmethod
    def _extract(data: str) -> tuple[str, Optional[str]]:
        m = DATA_URI_RE.match(data)
        if m:
            return m.group("data"), m.group("mime")
        return data, None

    @staticmethod
    def _decode_base64(payload: str, *, max_bytes: Optional[int] = None) -> bytes:
        if max_bytes is not None and len(payload) > ((max_bytes + 2) // 3) * 4 + 8:
            raise ValueError(f"Uploaded image exceeds {max_bytes} bytes")
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Uploaded asset is not valid base64") from error
        if max_bytes is not None and len(decoded) > max_bytes:
            raise ValueError(f"Uploaded image exceeds {max_bytes} bytes")
        return decoded

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _guess_ext(filename: Optional[str], mime: Optional[str]) -> str:
        if filename and Path(filename).suffix:
            return Path(filename).suffix
        if mime:
            guessed = mimetypes.guess_extension(mime)
            if guessed:
                return guessed
        return ".bin"
