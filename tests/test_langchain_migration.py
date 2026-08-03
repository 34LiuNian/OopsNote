from __future__ import annotations

import asyncio

from oopsnote.ai.langchain_tools import ContractBoundToolDispatcher, langchain_tool_schemas
from oopsnote.ai.providers import ProviderProfile
from oopsnote.ai.secrets import MemorySecretStore
from oopsnote.mcp import ocr
from oopsnote.core import AppSettingsStore, RunStore, TaskCreateRequest, TaskStore
from oopsnote.mcp.contracts import load_tool_contract


class FakeSecretStore:
    def __init__(self, present: set[str]) -> None:
        self.present = present

    def has(self, reference: str | None) -> bool:
        return reference in self.present


def test_provider_profile_public_view_never_exposes_credential_reference():
    profile = ProviderProfile(
        id="deepseek-primary",
        version=3,
        provider="deepseek",
        model="deepseek-v4-flash",
        base_url="https://provider.example/v1",
        credential_ref="opaque-reference",
    )

    assert profile.public_view(FakeSecretStore({"opaque-reference"})) == {
        "id": "deepseek-primary",
        "version": 3,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "base_url": "https://provider.example/v1",
        "enabled": True,
        "has_secret": True,
    }


def test_profile_store_replaces_only_same_or_newer_version(tmp_path):
    store = AppSettingsStore(tmp_path / "settings.json")
    first = ProviderProfile(
        id="deepseek-primary", version=1, provider="deepseek", model="m1",
        base_url="https://provider.example", credential_ref="one",
    )
    second = first.model_copy(update={"version": 2, "model": "m2", "credential_ref": "two"})
    store.upsert_provider_profile(first)
    store.upsert_provider_profile(second)

    assert store.provider_profiles() == [second]
    assert "two" in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_langchain_tools_are_derived_from_the_canonical_mcp_contract():
    contract = load_tool_contract()["tools"]
    schemas = langchain_tool_schemas()

    assert [item["function"]["name"] for item in schemas] == [item["name"] for item in contract]
    assert [item["function"]["parameters"] for item in schemas] == [item["parameters"] for item in contract]


def test_contract_dispatcher_only_accepts_canonical_tool_names():
    calls = []

    class Client:
        async def call(self, remote_name, arguments):
            calls.append((remote_name, arguments))
            return {"ok": True}

    dispatcher = ContractBoundToolDispatcher(Client())
    result = asyncio.run(dispatcher.call("ocr_image", {"task_id": "t", "run_id": "r"}))

    assert result == {"ok": True}
    assert calls == [("ocr_image", {"task_id": "t", "run_id": "r"})]


def test_contract_dispatcher_binds_model_calls_to_the_active_run():
    calls = []

    class Client:
        async def call(self, remote_name, arguments):
            calls.append((remote_name, arguments))
            return {"ok": True}

    dispatcher = ContractBoundToolDispatcher(Client(), task_id="active-task", run_id="active-run")
    asyncio.run(dispatcher.call("ocr_image", {}))

    assert calls == [("ocr_image", {"task_id": "active-task", "run_id": "active-run"})]
    try:
        asyncio.run(dispatcher.call("ocr_image", {"task_id": "other-task"}))
    except ValueError as error:
        assert "active task_id" in str(error)
    else:
        raise AssertionError("cross-task tool call was accepted")


def test_ocr_vault_configuration_does_not_fall_back_to_legacy_file(monkeypatch):
    vault = MemorySecretStore()
    reference = vault.put("vault-only-secret")
    ocr.configure_ocr_vault(vault, reference, model="vision", endpoint="https://ocr.example/v1")
    monkeypatch.delenv("OOPSNOTE_OCR_CONFIG", raising=False)

    try:
        config = ocr._load_ocr_config()
        assert config == {"dashscope_api_key": "vault-only-secret", "model": "vision", "endpoint": "https://ocr.example/v1"}
    finally:
        ocr.clear_ocr_vault()


def test_ocr_vault_state_is_explicit():
    ocr.clear_ocr_vault()
    assert not ocr.ocr_vault_is_configured()
    vault = MemorySecretStore()
    reference = vault.put("key")
    ocr.configure_ocr_vault(vault, reference, model="vision")
    try:
        assert ocr.ocr_vault_is_configured()
    finally:
        ocr.clear_ocr_vault()


def test_profile_snapshot_is_durable_when_settings_profile_rotates(tmp_path):
    settings = AppSettingsStore(tmp_path / "settings.json")
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    first = ProviderProfile(id="p", version=1, provider="deepseek", model="old", base_url="https://provider.example", credential_ref="old-ref")
    settings.upsert_provider_profile(first)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = run_store.create(task.id, backend="langchain", provider_profile_snapshot=first.model_dump(mode="json"))
    settings.upsert_provider_profile(first.model_copy(update={"version": 2, "model": "new", "credential_ref": "new-ref"}))

    assert run_store.get(run.id).provider_profile_snapshot["credential_ref"] == "old-ref"
    assert settings.provider_profiles()[0].credential_ref == "new-ref"


def test_langchain_event_writer_redacts_credentials(tmp_path):
    from oopsnote.ai.backends.langchain import LangChainRunner

    path = tmp_path / "events.jsonl"
    LangChainRunner._event(path, "run_started", {"model": "m", "credential_ref": "opaque", "secret": "never-log"})

    rendered = path.read_text(encoding="utf-8")
    assert "credential_ref" not in rendered
    assert "opaque" not in rendered
    assert "never-log" not in rendered


def test_api_defaults_to_langchain_backend():
    from oopsnote.api.main import _configured_backend

    assert _configured_backend(None) == "langchain"
