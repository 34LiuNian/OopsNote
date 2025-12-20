from fastapi.testclient import TestClient

from app.main import app


def test_agent_enabled_defaults_present() -> None:
    client = TestClient(app)
    res = client.get("/settings/agent-enabled")
    assert res.status_code == 200
    body = res.json()
    enabled = body["enabled"]
    # Keys exposed for UI stability
    assert set(enabled.keys()) == {"SOLVER", "TAGGER", "OCR"}
    # Non-disableable agents always true
    assert enabled["SOLVER"] is True
    assert enabled["TAGGER"] is True
    assert enabled["OCR"] is True


def test_agent_enabled_update_enforces_locked_agents() -> None:
    client = TestClient(app)

    res = client.put(
        "/settings/agent-enabled",
        json={
            "enabled": {
                "ocr": False,
                "solver": False,
                "tagger": False,
            }
        },
    )
    assert res.status_code == 200
    enabled = res.json()["enabled"]
    # Locked agents are forced to true
    assert enabled["OCR"] is True
    assert enabled["SOLVER"] is True
    assert enabled["TAGGER"] is True
