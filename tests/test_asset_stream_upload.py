import asyncio
import hashlib

import pytest

from oopsnote.core.assets import AssetStore, AssetUploadTooLargeError


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


def test_stream_upload_persists_only_a_complete_matching_source(tmp_path):
    store = AssetStore(tmp_path / "assets")
    source = b"scanned document source"
    source_hash = hashlib.sha256(source).hexdigest()

    asset_path = asyncio.run(
        store.save_stream(
            _chunks(source[:8], source[8:]),
            "questions.pdf",
            stable_name=f"batch-{source_hash}",
            expected_sha256=source_hash,
            max_bytes=len(source),
        )
    )

    assert store.resolve(asset_path).read_bytes() == source
    assert not list(store.base_dir.glob("*.uploading"))


def test_stream_upload_removes_partial_file_after_limit_or_hash_failure(tmp_path):
    store = AssetStore(tmp_path / "assets")

    with pytest.raises(AssetUploadTooLargeError):
        asyncio.run(
            store.save_stream(
                _chunks(b"abc", b"d"),
                "oversized.pdf",
                stable_name="batch-oversized",
                expected_sha256=hashlib.sha256(b"abcd").hexdigest(),
                max_bytes=3,
            )
        )
    with pytest.raises(ValueError, match="File hash mismatch"):
        asyncio.run(
            store.save_stream(
                _chunks(b"content"),
                "bad-hash.pdf",
                stable_name="batch-bad-hash",
                expected_sha256=hashlib.sha256(b"other").hexdigest(),
                max_bytes=16,
            )
        )

    assert list(store.base_dir.iterdir()) == []
