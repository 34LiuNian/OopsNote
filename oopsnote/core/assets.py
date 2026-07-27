"""资产文件存储。

图片 / PDF 以文件形式落盘，元数据记录相对路径。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


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

    def save_image_crop(
        self,
        source_asset_path: str,
        crop: Mapping[str, Any],
    ) -> tuple[str, dict[str, float]]:
        """Persist an idempotent PNG crop derived from one managed image asset."""
        normalized = self.normalize_crop_rect(crop)
        source_path = self.resolve(source_asset_path)
        source_bytes = source_path.read_bytes()
        crop_key = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        identity = hashlib.sha256(source_bytes + crop_key.encode("utf-8")).hexdigest()

        try:
            with Image.open(BytesIO(source_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
                width, height = image.size
                left = max(0, min(width - 1, math.floor(normalized["x"] * width)))
                top = max(0, min(height - 1, math.floor(normalized["y"] * height)))
                right = max(left + 1, min(width, math.ceil((normalized["x"] + normalized["width"]) * width)))
                bottom = max(top + 1, min(height, math.ceil((normalized["y"] + normalized["height"]) * height)))
                cropped = image.crop((left, top, right, bottom))
                if cropped.mode not in {"1", "L", "LA", "RGB", "RGBA"}:
                    cropped = cropped.convert("RGBA" if "transparency" in cropped.info else "RGB")
                output = BytesIO()
                cropped.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise ValueError("Task source asset is not a supported raster image") from error

        path = self.save_bytes(
            output.getvalue(),
            filename="diagram.png",
            stable_name=f"diagram-{identity}",
        )
        return path, normalized

    @staticmethod
    def normalize_crop_rect(crop: Mapping[str, Any]) -> dict[str, float]:
        if not isinstance(crop, Mapping):
            raise ValueError("diagram_image_crop must be an object")
        normalized: dict[str, float] = {}
        for key in ("x", "y", "width", "height"):
            value = crop.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"diagram_image_crop.{key} must be a finite number")
            normalized[key] = round(float(value), 8)
        if normalized["x"] < 0 or normalized["y"] < 0:
            raise ValueError("diagram_image_crop origin must be within the image")
        if normalized["width"] <= 0 or normalized["height"] <= 0:
            raise ValueError("diagram_image_crop dimensions must be positive")
        if normalized["x"] + normalized["width"] > 1.00000001 or normalized["y"] + normalized["height"] > 1.00000001:
            raise ValueError("diagram_image_crop must stay within the image")
        normalized["width"] = min(normalized["width"], 1 - normalized["x"])
        normalized["height"] = min(normalized["height"], 1 - normalized["y"])
        return normalized

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
