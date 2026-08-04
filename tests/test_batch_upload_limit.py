import hashlib

from fastapi.testclient import TestClient

from oopsnote.api import main
from oopsnote.api.routes import batch
from oopsnote.core import AssetStore, BatchSessionStore


def test_batch_source_limit_is_advertised_and_enforced_before_persistence(
    tmp_path, monkeypatch
):
    storage = tmp_path / "storage"
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(storage / "assets"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    monkeypatch.setattr(batch, "BATCH_SOURCE_MAX_BYTES", 3)
    client = TestClient(main.app)

    assert client.get("/batch-sessions/upload-limits").json() == {"source_max_bytes": 3}

    source = b"four"
    digest = hashlib.sha256(source).hexdigest()
    response = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={
            "content-type": "application/pdf",
            "x-oopsnote-filename": "oversized.pdf",
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Batch source exceeds the 3 byte limit"
    assert client.get(f"/batch-sessions/{digest}").status_code == 404

    accepted_source = b"abc"
    accepted_digest = hashlib.sha256(accepted_source).hexdigest()
    accepted = client.put(
        f"/batch-sessions/{accepted_digest}/source",
        content=accepted_source,
        headers={
            "content-type": "application/pdf",
            "x-oopsnote-filename": "accepted.pdf",
        },
    )

    assert accepted.status_code == 200
    assert client.get(f"/batch-sessions/{accepted_digest}").status_code == 200
