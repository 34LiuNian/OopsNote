"""资产文件存储。

图片 / PDF 以文件形式落盘，元数据记录相对路径。
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4


DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")


class AssetStore:
    """本地资产文件存储。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[1] / "storage" / "assets"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_base64(self, data: str, filename: Optional[str] = None) -> str:
        """保存 base64 字符串，返回相对路径。"""
        payload, mime = self._extract(data)
        ext = self._guess_ext(filename, mime)
        asset_id = uuid4().hex
        name = filename or f"{asset_id}{ext}"
        safe_name = name.replace("/", "_").replace("\\", "_")
        path = self.base_dir / safe_name
        path.write_bytes(base64.b64decode(payload))
        return f"/assets/{safe_name}"

    def save_file(self, source_path: str | Path) -> str:
        """复制文件到资产目录，返回相对路径。"""
        source = Path(source_path)
        asset_id = uuid4().hex
        ext = source.suffix or ".bin"
        name = f"{asset_id}{ext}"
        dest = self.base_dir / name
        dest.write_bytes(source.read_bytes())
        return f"/assets/{name}"

    def save_bytes(self, data: bytes, filename: str, stable_name: Optional[str] = None) -> str:
        """保存原始上传文件；stable_name 用于内容哈希去重。"""
        ext = Path(filename).suffix or ".bin"
        name = f"{stable_name}{ext}" if stable_name else f"{uuid4().hex}{ext}"
        safe_name = name.replace("/", "_").replace("\\", "_")
        path = self.base_dir / safe_name
        if not path.exists():
            path.write_bytes(data)
        return f"/assets/{safe_name}"

    @staticmethod
    def _extract(data: str) -> tuple[str, Optional[str]]:
        m = DATA_URI_RE.match(data)
        if m:
            return m.group("data"), m.group("mime")
        return data, None

    @staticmethod
    def _guess_ext(filename: Optional[str], mime: Optional[str]) -> str:
        if filename and Path(filename).suffix:
            return Path(filename).suffix
        if mime:
            guessed = mimetypes.guess_extension(mime)
            if guessed:
                return guessed
        return ".bin"
