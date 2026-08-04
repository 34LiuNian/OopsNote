from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from oopsnote.ai.langchain_tools import ContractBoundToolDispatcher, langchain_tool_schemas
from oopsnote.ai.providers import (
    ChannelModel,
    LangChainModelPolicy,
    ProviderCapabilities,
    ProviderChannel,
    ProviderClientFactory,
    ProviderConnectionError,
    ProviderProfile,
    ProviderValidationResult,
    StageModelSelection,
    collect_unreferenced_channel_secrets,
    profile_for_channel_model,
)
from oopsnote.ai.secrets import EncryptedFileSecretStore, MemorySecretStore, SecretStoreCorruptionError
from oopsnote.mcp import ocr
from oopsnote.core import AppSettingsStore, RunStatus, RunStore, TaskCreateRequest, TaskStatus, TaskStore
from oopsnote.mcp.contracts import load_tool_contract


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        del messages
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


class FakeProviderFactory:
    def __init__(self, model, secret_store):
        self.model = model
        self.secret_store = secret_store

    def create_chat_model(self, profile):
        del profile
        return self.model


class ReturningToolClient:
    async def call(self, remote_name, arguments):
        del remote_name, arguments
        return {"ok": True}


def model_response(round_number: int, *, tool: str | None = None, input_tokens: int = 0, output_tokens: int = 0):
    calls = [] if tool is None else [{"name": tool, "args": {}, "id": f"call-{round_number}"}]
    return SimpleNamespace(
        tool_calls=calls,
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        response_metadata={},
    )


def langchain_runner_fixture(tmp_path, model, tool_client=None, *, timeout_seconds=5):
    from oopsnote.ai.backends.langchain import LangChainRunner

    settings = AppSettingsStore(tmp_path / "settings.json")
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    vault = MemorySecretStore()
    reference = vault.put("provider-secret")
    channel = ProviderChannel(
        id="primary", version=1, display_name="Primary", provider="deepseek",
        base_url="https://provider.example", credential_ref=reference,
        models=(ChannelModel(
            id="model", source="DeepSeek", enabled=True,
            capability=ProviderCapabilities(tool_calling=True, vision=True),
        ),),
    )
    settings.upsert_provider_channel(channel)
    selection = StageModelSelection(channel_id=channel.id, model_id="model")
    settings.set_langchain_model_policy(LangChainModelPolicy(
        version=1, vision=selection, agent=selection, review=selection,
    ))
    factory = FakeProviderFactory(model, vault)
    runner = LangChainRunner(
        project_root=Path(__file__).resolve().parents[1],
        task_store=task_store,
        run_store=run_store,
        settings_store=settings,
        provider_factory=lambda: factory,
        tool_client_factory=lambda: tool_client or ReturningToolClient(),
        timeout_seconds=timeout_seconds,
        poll_seconds=0.01,
        heartbeat_seconds=0.05,
    )
    return runner, task_store, run_store, vault, profile_for_channel_model(channel, "model")


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

    public = profile.public_view(FakeSecretStore({"opaque-reference"}))
    assert public["id"] == "deepseek-primary"
    assert public["display_name"] == "deepseek-primary"
    assert public["version"] == 3
    assert public["provider"] == "deepseek"
    assert public["model"] == "deepseek-v4-flash"
    assert public["base_url"] == "https://provider.example/v1"
    assert public["enabled"] is True
    assert public["has_secret"] is True
    assert "credential_ref" not in public


@pytest.mark.parametrize(
    ("provider", "expects_json_mode"),
    [
        ("deepseek", True),
        ("openai", True),
        ("openai-compatible", True),
        ("anthropic", False),
        ("google", False),
    ],
)
def test_vision_ocr_model_uses_native_json_mode_only_when_supported(monkeypatch, provider, expects_json_mode):
    vault = MemorySecretStore()
    profile = ProviderProfile(
        id="vision", version=1, provider=provider, model="vision-model",
        base_url="https://provider.example/v1", credential_ref=vault.put("secret"),
    )
    calls = []

    class FakeModel:
        def bind(self, **kwargs):
            calls.append(kwargs)
            return "json-mode-model"

    factory = ProviderClientFactory(vault)
    monkeypatch.setattr(factory, "create_chat_model", lambda _profile: FakeModel())

    result = factory.create_vision_ocr_model(profile)

    if expects_json_mode:
        assert result == "json-mode-model"
        assert calls == [{"response_format": {"type": "json_object"}, "temperature": 0}]
    else:
        assert isinstance(result, FakeModel)
        assert calls == []


def test_provider_api_reports_unavailable_vault_instead_of_missing_secrets(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    settings.upsert_provider_channel(ProviderChannel(
        id="primary", version=1, display_name="Primary", provider="deepseek",
        base_url="https://provider.example/v1", credential_ref="missing-ref",
    ))
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "get_secret_store", lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))

    response = TestClient(main.app).get("/settings/ai/channels")

    assert response.status_code == 503
    assert response.json() == {"detail": "provider secret store is unavailable"}


def test_provider_api_reports_unreadable_vault_instead_of_crashing(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    settings.upsert_provider_channel(ProviderChannel(
        id="primary", version=1, display_name="Primary", provider="deepseek",
        base_url="https://provider.example/v1", credential_ref="unreadable-ref",
    ))

    class UnreadableVault:
        def has(self, _reference):
            raise SecretStoreCorruptionError("vault file cannot be read")

    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "get_secret_store", lambda: UnreadableVault())

    response = TestClient(main.app).get("/settings/ai/channels")

    assert response.status_code == 503
    assert response.json() == {"detail": "provider secret store is unavailable"}


def test_task_provider_options_endpoint_is_removed():
    from oopsnote.api import main

    assert TestClient(main.app).get("/ai/provider-options").status_code == 404


def test_model_policy_selects_the_vision_stage(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    reference = vault.put("ocr-secret")
    channel = ProviderChannel(
        id="ocr", version=1, display_name="OCR", provider="openai-compatible",
        base_url="https://ocr.example/v1", credential_ref=reference,
        models=(
            ChannelModel(id="vision-model", source="OCR", enabled=True, capability=ProviderCapabilities(vision=True)),
            ChannelModel(id="agent-model", source="OCR", enabled=True, capability=ProviderCapabilities(tool_calling=True)),
        ),
    )
    settings.upsert_provider_channel(channel)
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    response = TestClient(main.app).put("/settings/ai/policy", json={
        "vision": {"channel_id": "ocr", "model_id": "vision-model"},
        "agent": {"channel_id": "ocr", "model_id": "agent-model"},
        "review": {"channel_id": "ocr", "model_id": "agent-model"},
    })

    assert response.status_code == 200
    assert settings.langchain_model_policy().vision == StageModelSelection(channel_id="ocr", model_id="vision-model")

    disabled = TestClient(main.app).patch(
        "/settings/ai/channels/ocr/models/vision-model",
        json={"enabled": False},
    )

    assert disabled.status_code == 200
    assert disabled.json()["policy_cleared"] is True
    assert settings.langchain_model_policy() is None


def test_provider_rotation_commits_a_validated_new_nonsecret_version(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    old_reference = vault.put("old-secret")
    old = ProviderChannel(
        id="primary", version=3, display_name="Primary", provider="deepseek",
        base_url="https://old.example/v1", credential_ref=old_reference,
        models=(ChannelModel(id="old-model", source="DeepSeek", enabled=True, capability=ProviderCapabilities(tool_calling=True)),),
    )
    settings.upsert_provider_channel(old)
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    with patch("oopsnote.api.routes.ai_settings.ProviderClientFactory.discover_models", return_value=[
        ChannelModel(id="old-model", source="DeepSeek"),
    ]):
        response = TestClient(main.app).post(
            "/settings/ai/channels/primary/credential",
            json={"secret": "new-secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "credential_ref" not in str(body)
    assert body["channel"]["version"] == 4
    assert body["channel"]["provider"] == "deepseek"
    assert body["channel"]["models"][0]["capability"]["tool_calling"] is True
    assert body["validation"]["success"] is True
    assert body["validation"]["provider"] == "deepseek"
    assert body["validation"]["model"] == "catalog"
    assert body["validation"]["error_code"] is None
    assert body["validation"]["message"] == "Credentials and model catalog validated"
    assert isinstance(body["validation"]["latency_ms"], int)
    assert body["validation"]["tested_at"]
    assert "credential_ref" not in str(body["validation"])
    current = settings.provider_channels()[0]
    assert vault.get(current.credential_ref) == "new-secret"
    assert not vault.has(old_reference)


def test_rotating_a_channel_does_not_change_the_global_policy(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    active = ProviderChannel(
        id="active", version=1, display_name="Active", provider="deepseek",
        base_url="https://active.example/v1", credential_ref=vault.put("active-secret"),
        models=(ChannelModel(id="active-model", source="DeepSeek", enabled=True, capability=ProviderCapabilities(tool_calling=True, vision=True)),),
    )
    inactive = ProviderChannel(
        id="inactive", version=1, display_name="Inactive", provider="deepseek",
        base_url="https://inactive.example/v1", credential_ref=vault.put("old-secret"),
        models=(ChannelModel(id="old-model", source="DeepSeek"),),
    )
    settings.upsert_provider_channel(active)
    settings.upsert_provider_channel(inactive)
    selection = StageModelSelection(channel_id="active", model_id="active-model")
    settings.set_langchain_model_policy(LangChainModelPolicy(version=1, vision=selection, agent=selection, review=selection))
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    with patch("oopsnote.api.routes.ai_settings.ProviderClientFactory.discover_models", return_value=[ChannelModel(id="old-model", source="DeepSeek")]):
        response = TestClient(main.app).post(
            "/settings/ai/channels/inactive/credential",
            json={"secret": "new-secret"},
        )

    assert response.status_code == 200
    assert settings.langchain_model_policy().agent == selection
    channels = {channel.id: channel for channel in settings.provider_channels()}
    assert channels["inactive"].version == 2


def test_failed_provider_validation_keeps_previous_profile_and_secret(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    old_reference = vault.put("old-secret")
    channel = ProviderChannel(
        id="primary", version=2, display_name="Primary", provider="deepseek",
        base_url="https://provider.example/v1", credential_ref=old_reference,
    )
    settings.upsert_provider_channel(channel)
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)
    validation = ProviderValidationResult(
        success=False,
        provider="deepseek",
        model="model",
        error_code="authentication_failed",
        message="Provider connection validation failed",
    )

    with patch("oopsnote.api.routes.ai_settings.ProviderClientFactory.discover_models", side_effect=ProviderConnectionError(validation)):
        response = TestClient(main.app).post(
            "/settings/ai/channels/primary/credential",
            json={"secret": "invalid-secret"},
        )

    assert response.status_code == 422
    assert settings.provider_channels() == [channel]
    assert vault.get(old_reference) == "old-secret"
    assert len(vault._values) == 1


def test_encrypted_file_store_never_writes_plaintext_and_rejects_wrong_key(tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_bytes(EncryptedFileSecretStore.generate_key())
    path = tmp_path / "vault" / "credentials.json"
    store = EncryptedFileSecretStore(path, key_file)

    reference = store.put("never-write-this-secret")

    assert store.get(reference) == "never-write-this-secret"
    assert b"never-write-this-secret" not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    wrong_key = tmp_path / "wrong.key"
    wrong_key.write_bytes(EncryptedFileSecretStore.generate_key())
    with pytest.raises(SecretStoreCorruptionError):
        EncryptedFileSecretStore(path, wrong_key).get(reference)


def test_secret_store_key_initialization_is_idempotent(tmp_path):
    from scripts.setup.init_secret_store import initialize

    path = tmp_path / "secrets" / "credential_store_key"
    assert initialize(path)
    original = path.read_bytes()
    assert not initialize(path)
    assert path.read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600


def test_legacy_model_and_ocr_import_create_channels_without_persisting_secrets(tmp_path):
    from scripts.migrate_local_secrets import import_model_channel, import_ocr_channel

    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"deepseek": {"key": "model-secret"}}), encoding="utf-8")
    extensions = tmp_path / "extensions.json"
    extensions.write_text(json.dumps({
        "ocr_image": {
            "dashscope_api_key": "ocr-secret",
            "model": "vision-model",
            "endpoint": "https://ocr.example/v1",
        }
    }), encoding="utf-8")
    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()

    model_channel = import_model_channel(
        auth,
        store=vault,
        settings=settings,
        channel_id="primary",
        provider="deepseek",
        model="chat-model",
        base_url="https://provider.example/v1",
    )
    ocr_channel = import_ocr_channel(
        extensions,
        store=vault,
        settings=settings,
        channel_id="ocr",
    )

    persisted = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "model-secret" not in persisted
    assert "ocr-secret" not in persisted
    assert vault.get(model_channel.credential_ref) == "model-secret"
    assert vault.get(ocr_channel.credential_ref) == "ocr-secret"
    assert settings.provider_channels() == [model_channel, ocr_channel]
    assert all(not item.enabled for channel in settings.provider_channels() for item in channel.models)


def test_reference_collection_waits_for_active_runs_then_deletes_old_secret(tmp_path):
    vault = MemorySecretStore()
    old_reference = vault.put("old")
    current_reference = vault.put("current")
    profile = ProviderProfile(
        id="primary", version=2, provider="deepseek", model="m",
        base_url="https://provider.example", credential_ref=current_reference,
    )
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = run_store.create(
        task.id,
        backend="langchain",
        provider_profile_snapshot=profile.model_copy(
            update={"version": 1, "credential_ref": old_reference}
        ).model_dump(mode="json"),
    )

    assert collect_unreferenced_channel_secrets(vault, [profile], run_store.list_all()) == 0
    assert vault.has(old_reference)
    run_store.finish(run.id, RunStatus.FAILED)

    assert collect_unreferenced_channel_secrets(vault, [profile], run_store.list_all()) == 1
    assert not vault.has(old_reference)
    assert vault.has(current_reference)


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


def test_contract_dispatcher_preserves_terminal_write_barriers():
    events = []

    class Client:
        async def call(self, remote_name, arguments):
            events.append(("start", remote_name))
            if remote_name != "finalize_task":
                await asyncio.sleep(0.01)
            events.append(("end", remote_name))
            return {"ok": True}

    dispatcher = ContractBoundToolDispatcher(Client(), task_id="t", run_id="r")
    calls = [
        {"name": "mcp__oopsnote_pipeline_get_task", "args": {}, "id": "1"},
        {"name": "mcp__oopsnote_pipeline_list_tags", "args": {}, "id": "2"},
        {"name": "mcp__oopsnote_pipeline_finalize_task", "args": {"problem_json": "{}"}, "id": "3"},
    ]

    results = asyncio.run(dispatcher.call_many(calls))

    finalize_start = events.index(("start", "finalize_task"))
    assert events.index(("end", "get_task")) < finalize_start
    assert events.index(("end", "list_tags")) < finalize_start
    assert results == [{"ok": True}, {"ok": True}, {"ok": True}]


def test_contract_dispatcher_uses_canonical_barriers_for_all_state_writes():
    events = []

    class Client:
        async def call(self, remote_name, arguments):
            del arguments
            events.append(("start", remote_name))
            if remote_name in {"get_task", "list_tags"}:
                await asyncio.sleep(0.01)
            events.append(("end", remote_name))
            return {"ok": True}

    dispatcher = ContractBoundToolDispatcher(Client(), task_id="t", run_id="r")
    calls = [
        {"name": "mcp__oopsnote_pipeline_get_task", "args": {}, "id": "1"},
        {"name": "mcp__oopsnote_pipeline_create_tag", "args": {"dimension": "error", "value": "x"}, "id": "2"},
        {"name": "mcp__oopsnote_pipeline_list_tags", "args": {"dimension": "error"}, "id": "3"},
    ]

    asyncio.run(dispatcher.call_many(calls))

    assert events.index(("end", "get_task")) < events.index(("start", "create_tag"))
    assert events.index(("end", "create_tag")) < events.index(("start", "list_tags"))


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


def test_stage_snapshot_is_durable_when_channel_rotates(tmp_path):
    settings = AppSettingsStore(tmp_path / "settings.json")
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    first = ProviderChannel(
        id="p", version=1, display_name="P", provider="deepseek",
        base_url="https://provider.example", credential_ref="old-ref",
        models=(ChannelModel(id="old", source="DeepSeek", enabled=True, capability=ProviderCapabilities(tool_calling=True, vision=True)),),
    )
    settings.upsert_provider_channel(first)
    task = task_store.create(TaskCreateRequest(subject="math"))
    profile = profile_for_channel_model(first, "old")
    run = run_store.create(task.id, backend="langchain", provider_profile_snapshot={"policy_version": 1, "vision": profile.model_dump(mode="json"), "agent": profile.model_dump(mode="json"), "review": profile.model_dump(mode="json")})
    settings.upsert_provider_channel(first.model_copy(update={"version": 2, "credential_ref": "new-ref"}))

    assert run_store.get(run.id).provider_profile_snapshot["agent"]["credential_ref"] == "old-ref"
    assert settings.provider_channels()[0].credential_ref == "new-ref"


def test_global_stage_policy_is_frozen_at_run_admission(tmp_path):
    model = ScriptedModel([model_response(1)])
    runner, task_store, run_store, vault, _ = langchain_runner_fixture(tmp_path, model)
    selected = ProviderChannel(
        id="selected", version=4, display_name="Selected", provider="openai-compatible",
        base_url="https://selected.example/v1", credential_ref=vault.put("selected-secret"),
        models=(ChannelModel(id="selected-model", source="Selected", enabled=True, capability=ProviderCapabilities(tool_calling=True, vision=True)),),
    )
    runner.settings_store.upsert_provider_channel(selected)
    selection = StageModelSelection(channel_id="selected", model_id="selected-model")
    runner.settings_store.set_langchain_model_policy(LangChainModelPolicy(version=2, vision=selection, agent=selection, review=selection))
    task = task_store.create(TaskCreateRequest(subject="math"))

    run = runner.enqueue(task.id)
    runner.settings_store.upsert_provider_channel(selected.model_copy(update={"version": 5}))

    assert run.provider == "openai-compatible"
    assert run.model == "selected-model"
    assert run.provider_profile_snapshot["policy_version"] == 2
    assert run.provider_profile_snapshot["agent"]["model"] == "selected-model"


def test_provider_channel_used_by_active_run_cannot_be_deleted(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    channel = ProviderChannel(
        id="active", version=1, display_name="Active", provider="deepseek",
        credential_ref=vault.put("secret"),
    )
    settings.upsert_provider_channel(channel)
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    task = task_store.create(TaskCreateRequest(subject="math"))
    run_store.create(
        task.id,
        backend="langchain",
        provider_profile_snapshot={"agent": {"channel_id": channel.id, "credential_ref": channel.credential_ref}},
    )
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    response = TestClient(main.app).delete("/settings/ai/channels/active")

    assert response.status_code == 409
    assert response.json() == {"detail": "channel_in_use"}
    assert settings.provider_channels() == [channel]
    assert vault.has(channel.credential_ref)


def test_fresh_retry_keeps_failed_run_profile_snapshot(tmp_path):
    from oopsnote.ai.backends.langchain import LangChainRunner

    settings = AppSettingsStore(tmp_path / "settings.json")
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    old = ProviderChannel(
        id="p", version=1, display_name="P", provider="deepseek",
        base_url="https://provider.example", credential_ref="old-ref",
        models=(ChannelModel(id="old", source="DeepSeek", enabled=True, capability=ProviderCapabilities(tool_calling=True, vision=True)),),
    )
    settings.upsert_provider_channel(old)
    selection = StageModelSelection(channel_id="p", model_id="old")
    settings.set_langchain_model_policy(LangChainModelPolicy(version=1, vision=selection, agent=selection, review=selection))
    runner = LangChainRunner(
        project_root=Path(__file__).resolve().parents[1],
        task_store=task_store,
        run_store=run_store,
        settings_store=settings,
        provider_factory=lambda: SimpleNamespace(secret_store=MemorySecretStore()),
        tool_client_factory=lambda: None,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    failed = run_store.create(
        task.id,
        backend="langchain",
        provider="deepseek",
        model="old",
        prompt_version=runner.prompt_version,
        provider_profile_snapshot={
            "policy_version": 1,
            "vision": profile_for_channel_model(old, "old").model_dump(mode="json"),
            "agent": profile_for_channel_model(old, "old").model_dump(mode="json"),
            "review": profile_for_channel_model(old, "old").model_dump(mode="json"),
        },
    )
    run_store.finish(failed.id, RunStatus.FAILED)
    task_store.mark_status(task.id, TaskStatus.FAILED, "transient")
    settings.upsert_provider_channel(old.model_copy(update={"version": 2, "credential_ref": "new-ref"}))

    retry = runner.enqueue(task.id, retry_of=run_store.get(failed.id))

    assert retry.provider_profile_snapshot == failed.provider_profile_snapshot
    assert retry.model == "old"


def test_provider_factory_leaves_run_timeout_to_managed_lifecycle(monkeypatch):
    captured = {}

    class ChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=ChatModel))
    vault = MemorySecretStore()
    reference = vault.put("secret")
    profile = ProviderProfile(
        id="p", version=1, provider="openai-compatible", model="m",
        base_url="https://provider.example", credential_ref=reference,
    )

    ProviderClientFactory(vault).create_chat_model(profile)

    assert captured["api_key"] == "secret"
    assert captured["max_retries"] == 0
    assert "timeout" not in captured


def test_langchain_runner_enforces_24_round_limit_and_accumulates_usage(tmp_path):
    response = model_response(
        1,
        tool="mcp__oopsnote_pipeline_get_task",
        input_tokens=2,
        output_tokens=3,
    )
    model = ScriptedModel([response])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    completed = run_store.get(run.id)
    assert model.calls == 24
    assert completed.status == RunStatus.FAILED
    assert completed.error_code == "not_finalized"
    assert completed.input_tokens == 48
    assert completed.output_tokens == 72
    assert task_store.get(task.id).status == TaskStatus.FAILED
    assert runner.prompt_version.startswith("oopsnote-skills-sha256:")
    assert "oopsnote-orchestrator" in runner._skill_pack


def test_langchain_timeout_covers_inflight_tool_call(tmp_path):
    started = threading.Event()

    class BlockingToolClient:
        async def call(self, remote_name, arguments):
            del remote_name, arguments
            started.set()
            await asyncio.Event().wait()

    model = ScriptedModel([model_response(1, tool="mcp__oopsnote_pipeline_get_task")])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(
        tmp_path, model, BlockingToolClient(), timeout_seconds=1
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    assert started.is_set()
    assert run_store.get(run.id).status == RunStatus.TIMED_OUT
    assert run_store.get(run.id).error_code == "process_timeout"


@pytest.mark.parametrize("phase", ["model", "tool"])
def test_langchain_cancel_stops_active_async_work_without_overwriting_terminal_state(tmp_path, phase):
    started = threading.Event()

    class BlockingModel(ScriptedModel):
        async def ainvoke(self, messages):
            if phase == "model":
                started.set()
                await asyncio.Event().wait()
            return await super().ainvoke(messages)

    class BlockingToolClient:
        async def call(self, remote_name, arguments):
            del remote_name, arguments
            started.set()
            await asyncio.Event().wait()

    model = BlockingModel([model_response(1, tool="mcp__oopsnote_pipeline_get_task")])
    tool_client = BlockingToolClient() if phase == "tool" else ReturningToolClient()
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(
        tmp_path, model, tool_client, timeout_seconds=10
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    thread = threading.Thread(target=runner.run, args=(task.id, run.id))
    try:
        thread.start()
        assert started.wait(timeout=3)
        runner.cancel(task.id)
        thread.join(timeout=3)
    finally:
        ocr.clear_ocr_vault()

    assert not thread.is_alive()
    assert task_store.get(task.id).status == TaskStatus.CANCELLED
    assert run_store.get(run.id).status == RunStatus.CANCELLED


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "provider_authorization"), (403, "provider_authorization"), (429, "rate_limit"), (503, "provider_unavailable"), (404, "runner_error")],
)
def test_langchain_provider_status_classification(status, expected):
    from oopsnote.ai.backends.langchain import LangChainRunner

    error = RuntimeError("provider failed")
    error.status_code = status
    assert LangChainRunner._error_code(error) == expected


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

    assert _configured_backend() == "langchain"


def test_task_and_batch_admission_do_not_expose_task_backend_selection():
    from oopsnote.api.main import app

    schema = app.openapi()
    for path in (
        "/tasks/{task_id}/process",
        "/tasks/{task_id}/retry",
        "/batch-sessions/{file_hash}/process",
    ):
        parameters = schema["paths"][path]["post"].get("parameters", [])
        assert "backend" not in {parameter["name"] for parameter in parameters}
