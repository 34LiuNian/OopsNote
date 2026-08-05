from __future__ import annotations

import asyncio
import json
import os
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
from oopsnote.core import AppSettingsStore, RunStatus, RunStore, TaskCreateRequest, TaskStage, TaskStatus, TaskStore
from oopsnote.mcp.contracts import load_tool_contract


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.bound_tools = None
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.messages.append(list(messages))
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

    def bind_managed_tools(
        self,
        model,
        profile,
        *,
        tool_names=None,
        constants=None,
        required_arguments=None,
        parameter_overrides=None,
    ):
        del profile
        return model.bind_tools(langchain_tool_schemas(
            tool_names,
            constants=constants,
            required_arguments=required_arguments,
            parameter_overrides=parameter_overrides,
        ))


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


def test_new_discovered_models_enable_tool_calling_by_default():
    model = ChannelModel(id="new-model", source="DeepSeek")

    assert model.capability.tool_calling is True
    assert model.capability.vision is False


def test_admin_can_reveal_one_channel_credential_without_cache_headers(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    reference = vault.put("stored-secret")
    settings.upsert_provider_channel(ProviderChannel(
        id="primary",
        version=1,
        display_name="Primary",
        provider="deepseek",
        credential_ref=reference,
    ))
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    response = TestClient(main.app).get("/settings/ai/channels/primary/credential")

    assert response.status_code == 200
    assert response.json() == {"secret": "stored-secret"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert settings.provider_channels()[0].credential_ref == reference


def test_revealing_a_missing_channel_credential_is_explicit(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    settings.upsert_provider_channel(ProviderChannel(
        id="primary",
        version=1,
        display_name="Primary",
        provider="deepseek",
    ))
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", MemorySecretStore)

    response = TestClient(main.app).get("/settings/ai/channels/primary/credential")

    assert response.status_code == 404
    assert response.json()["detail"] == "channel has no credential"


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
    if os.name != "nt":
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
    if os.name != "nt":
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


def test_contract_dispatcher_rejects_stale_phase_call_before_mcp_execution():
    calls = []

    class Client:
        async def call(self, remote_name, arguments):
            calls.append((remote_name, arguments))
            return {"ok": True}

    dispatcher = ContractBoundToolDispatcher(Client(), task_id="active-task", run_id="active-run")
    [schema] = langchain_tool_schemas(
        ["mcp__oopsnote_pipeline_list_tags"],
        constants={"mcp__oopsnote_pipeline_list_tags": {"dimension": "error"}},
    )
    result = asyncio.run(dispatcher.call_many(
        [{
            "name": "mcp__oopsnote_pipeline_list_tags",
            "args": {"dimension": "knowledge"},
            "id": "stale-call",
        }],
        allowed_parameters={
            schema["function"]["name"]: schema["function"]["parameters"],
        },
    ))

    assert isinstance(result[0], ValueError)
    assert "current pipeline transition" in str(result[0])
    assert calls == []


def test_contract_dispatcher_binds_authoritative_phase_arguments():
    calls = []

    class Client:
        async def call(self, remote_name, arguments):
            calls.append((remote_name, arguments))
            return {"ok": True}

    name = "mcp__oopsnote_pipeline_list_tags"
    constants = {name: {"dimension": "knowledge", "subject": "数学", "scope": "core"}}
    [schema] = langchain_tool_schemas([name], constants=constants)
    dispatcher = ContractBoundToolDispatcher(Client(), task_id="active-task", run_id="active-run")

    result = asyncio.run(dispatcher.call_many(
        [{
            "name": name,
            "args": {"dimension": "error", "subject": "math"},
            "id": "call-1",
        }],
        allowed_parameters={name: schema["function"]["parameters"]},
        fixed_arguments=constants,
    ))

    assert result == [{"ok": True}]
    assert calls == [("list_tags", {
        "dimension": "knowledge",
        "subject": "数学",
        "scope": "core",
        "task_id": "active-task",
        "run_id": "active-run",
    })]


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
    assert captured["base_url"] == "https://provider.example/v1"
    assert captured["max_retries"] == 0
    assert "timeout" not in captured


def test_provider_factory_configures_dashscope_non_thinking_tool_loop(monkeypatch):
    captured = {}

    class ChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bind_tools(self, tools, **kwargs):
            captured["tools"] = tools
            captured["bind_kwargs"] = kwargs
            return self

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=ChatModel))
    vault = MemorySecretStore()
    reference = vault.put("secret")
    profile = ProviderProfile(
        id="p", version=1, provider="openai", model="qwen3.7-flash",
        base_url="https://llm-b36ftbhf6tqtv374.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        credential_ref=reference,
    )

    factory = ProviderClientFactory(vault)
    model = factory.create_chat_model(profile)
    factory.bind_managed_tools(model, profile)

    assert captured["extra_body"] == {"enable_thinking": False}
    assert captured["bind_kwargs"] == {"tool_choice": "required", "parallel_tool_calls": False}


def test_provider_factory_configures_deepseek_non_thinking_tool_loop(monkeypatch):
    captured = {}

    class ChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bind_tools(self, tools, **kwargs):
            captured["tools"] = tools
            captured["bind_kwargs"] = kwargs
            return self

    monkeypatch.setitem(sys.modules, "langchain_deepseek", SimpleNamespace(ChatDeepSeek=ChatModel))
    vault = MemorySecretStore()
    profile = ProviderProfile(
        id="p", version=1, provider="deepseek", model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1", credential_ref=vault.put("secret"),
    )

    factory = ProviderClientFactory(vault)
    model = factory.create_chat_model(profile)
    factory.bind_managed_tools(model, profile)

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured["temperature"] == 0
    assert captured["max_tokens"] == 8192
    assert captured["bind_kwargs"] == {"tool_choice": "required", "parallel_tool_calls": False}


def test_langchain_places_immutable_rules_in_system_message(tmp_path):
    from langchain_core.messages import HumanMessage, SystemMessage

    model = ScriptedModel([model_response(1)])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math", metadata={"notes": "untrusted"}))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    assert isinstance(model.messages[0][0], SystemMessage)
    assert "submit_solution_candidate exactly once" in model.messages[0][0].content
    assert "problem_json at most 8000 characters" in model.messages[0][0].content
    assert isinstance(model.messages[0][1], HumanMessage)
    assert "Untrusted task context follows" in model.messages[0][1].content


def test_langchain_phase_tool_sets_are_disjoint_from_illegal_capabilities():
    from oopsnote.ai.backends.langchain import LangChainRunner

    assert "ocr_image" in LangChainRunner._SOLVER_TOOL_NAMES
    assert "mcp__oopsnote_pipeline_submit_solution_candidate" in LangChainRunner._SOLVER_TOOL_NAMES
    assert "mcp__oopsnote_pipeline_ocr_image" not in LangChainRunner._REVIEW_TOOL_NAMES
    assert "ocr_image" not in LangChainRunner._REVIEW_TOOL_NAMES
    assert "mcp__oopsnote_pipeline_finalize_task" in LangChainRunner._REVIEW_TOOL_NAMES
    assert "mcp__oopsnote_pipeline_submit_solution_candidate" not in LangChainRunner._REVIEW_TOOL_NAMES


def test_langchain_tag_selection_advances_to_error_catalog_without_branch_metadata():
    from oopsnote.ai.backends.langchain import LangChainRunner

    runner = object.__new__(LangChainRunner)
    task = SimpleNamespace(
        stage=TaskStage.TAGGING,
        subject="math",
        metadata={"_managed_tag_selection": {
            "run_id": "run-1",
            "subject": "math",
            "scope": "core",
            "branch_ids": ["algebra"],
        }},
    )
    run = SimpleNamespace(id="run-1", solution_candidate=SimpleNamespace(problem=SimpleNamespace(subject="math")))

    names, constants, required, overrides = runner._tool_binding_for(
        task=task,
        run=run,
        verification_context=True,
    )

    assert names == frozenset({runner._LIST_TAGS_TOOL})
    assert constants[runner._LIST_TAGS_TOOL]["dimension"] == "error"
    assert required == {}
    assert overrides == {}


def test_langchain_tool_schema_restrictions_are_derived_without_mutating_contract():
    before = load_tool_contract()
    tool_name = "mcp__oopsnote_pipeline_list_tags"

    [schema] = langchain_tool_schemas(
        [tool_name],
        constants={tool_name: {"dimension": "knowledge", "subject": "math"}},
        required_arguments={tool_name: ("branch_ids",)},
        parameter_overrides={tool_name: {"branch_ids": {
            "items": {"type": "string", "enum": ["algebra"]},
            "minItems": 1,
            "maxItems": 1,
            "type": "array",
        }}},
    )
    parameters = schema["function"]["parameters"]

    assert schema["function"]["name"] == tool_name
    assert parameters["properties"]["dimension"]["const"] == "knowledge"
    assert parameters["properties"]["subject"]["const"] == "math"
    assert parameters["properties"]["branch_ids"]["items"]["enum"] == ["algebra"]
    assert "branch_ids" in parameters["required"]
    assert load_tool_contract() == before


def test_tool_call_summary_redacts_content_and_keeps_repeat_fingerprint():
    from oopsnote.ai.backends.langchain import LangChainRunner

    call = {
        "name": "mcp__oopsnote_pipeline_list_tags",
        "args": {"dimension": "knowledge", "branch_ids": ["algebra"], "message": "untrusted content"},
    }
    summary = LangChainRunner._tool_call_summary(call)

    assert summary["name"] == call["name"]
    assert summary["dimension"] == "knowledge"
    assert summary["branch_ids_count"] == 1
    assert summary["message_bytes"] == len("untrusted content")
    assert "untrusted content" not in json.dumps(summary)


def test_tool_result_summary_does_not_persist_error_content():
    from oopsnote.ai.backends.langchain import LangChainRunner

    summary = LangChainRunner._tool_result_summary(ValueError("untrusted task content"))

    assert summary["ok"] is False
    assert summary["error_type"] == "ValueError"
    assert "untrusted task content" not in json.dumps(summary)


def test_langchain_no_tool_event_does_not_persist_model_content(tmp_path):
    model = ScriptedModel([SimpleNamespace(
        tool_calls=[],
        invalid_tool_calls=[],
        content="model text must not be persisted",
        usage_metadata={},
        response_metadata={"finish_reason": "stop"},
        additional_kwargs={},
    )])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    event_text = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert '"event": "model_no_tool_call"' in event_text
    assert "model text must not be persisted" not in event_text


def test_langchain_invalid_tool_call_has_bounded_in_run_recovery(tmp_path):
    invalid = SimpleNamespace(
        tool_calls=[],
        invalid_tool_calls=[{"name": "mcp__oopsnote_pipeline_submit_solution_candidate", "args": "", "error": "truncated"}],
        content="",
        usage_metadata={},
        response_metadata={"finish_reason": "length"},
        additional_kwargs={},
    )
    model = ScriptedModel([invalid])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    events = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert events.count('"event": "invalid_tool_recovery"') == 2
    assert run_store.get(run.id).error_code == "not_finalized"


def test_langchain_invalid_tool_calls_are_acknowledged_before_next_model_request(tmp_path):
    raw_calls = [
        {"id": "bad-1", "type": "function", "function": {"name": "first", "arguments": "{"}},
        {"id": "bad-2", "type": "function", "function": {"name": "second", "arguments": "{"}},
    ]
    invalid = SimpleNamespace(
        tool_calls=[],
        invalid_tool_calls=[
            {"id": "bad-1", "name": "first", "args": "{", "error": "truncated"},
            {"id": "bad-2", "name": "second", "args": "{", "error": "truncated"},
        ],
        content="",
        usage_metadata={},
        response_metadata={"finish_reason": "tool_calls"},
        additional_kwargs={"tool_calls": raw_calls},
    )
    model = ScriptedModel([invalid])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    second_request = model.messages[1]
    assert [message.tool_call_id for message in second_request if hasattr(message, "tool_call_id")] == [
        "bad-1",
        "bad-2",
    ]
    events = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert '"history_action": "tool_results"' in events


def test_langchain_truncated_tool_call_is_removed_even_when_ids_are_complete(tmp_path):
    invalid = SimpleNamespace(
        tool_calls=[],
        invalid_tool_calls=[{"id": "bad-1", "name": "candidate", "args": "{", "error": "truncated"}],
        content="",
        usage_metadata={},
        response_metadata={"finish_reason": "length"},
        additional_kwargs={"tool_calls": [{
            "id": "bad-1",
            "type": "function",
            "function": {"name": "candidate", "arguments": "{"},
        }]},
    )
    model = ScriptedModel([invalid])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    assert invalid not in model.messages[1]
    assert not any(hasattr(message, "tool_call_id") for message in model.messages[1])
    events = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert '"history_action": "truncated_response_removed"' in events


def test_langchain_invalid_tool_call_without_id_is_removed_from_history(tmp_path):
    invalid = SimpleNamespace(
        tool_calls=[],
        invalid_tool_calls=[{"name": "candidate", "args": "{", "error": "truncated"}],
        content="",
        usage_metadata={},
        response_metadata={"finish_reason": "tool_calls"},
        additional_kwargs={"tool_calls": [{
            "type": "function",
            "function": {"name": "candidate", "arguments": "{"},
        }]},
    )
    model = ScriptedModel([invalid])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(tmp_path, model)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    assert invalid not in model.messages[1]
    events = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert '"history_action": "response_removed"' in events


def test_langchain_tool_execution_error_adds_bounded_current_binding_recovery(tmp_path):
    class ErrorToolClient:
        async def call(self, remote_name, arguments):
            del remote_name, arguments
            raise ValueError("deterministic pipeline validation error")

    model = ScriptedModel([model_response(1, tool="mcp__oopsnote_pipeline_report_task_stage")])
    runner, task_store, run_store, vault, profile = langchain_runner_fixture(
        tmp_path,
        model,
        ErrorToolClient(),
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    ocr.configure_ocr_vault(vault, profile.credential_ref, model="ocr")
    try:
        runner.run(task.id, run.id)
    finally:
        ocr.clear_ocr_vault()

    assert any(
        "emit exactly one call to the tool currently bound" in message.content
        for message in model.messages[1]
        if hasattr(message, "content")
    )
    events = (run_store.base_dir / f"{run.id}.events.jsonl").read_text(encoding="utf-8")
    assert events.count('"event": "tool_execution_recovery"') == 2


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

    model = ScriptedModel([SimpleNamespace(
        tool_calls=[{
            "name": "mcp__oopsnote_pipeline_report_task_stage",
            "args": {"stage": "ocr"},
            "id": "call-1",
        }],
        usage_metadata={},
        response_metadata={},
    )])
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

    model = BlockingModel([model_response(1, tool="mcp__oopsnote_pipeline_report_task_stage")])
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
