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
from oopsnote.ai.providers import ProviderClientFactory, ProviderProfile, collect_unreferenced_profile_secrets
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
    profile = ProviderProfile(
        id="primary", version=1, provider="deepseek", model="model",
        base_url="https://provider.example", credential_ref=reference,
    )
    settings.activate_provider_profile(profile)
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
    return runner, task_store, run_store, vault, profile


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


def test_provider_api_reports_unavailable_vault_instead_of_missing_secrets(monkeypatch, tmp_path):
    from oopsnote.api import main

    monkeypatch.setattr(main, "APP_SETTINGS_STORE", AppSettingsStore(tmp_path / "settings.json"))
    monkeypatch.setattr(main, "get_secret_store", lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))

    response = TestClient(main.app).get("/settings/provider-profiles")

    assert response.status_code == 503
    assert response.json() == {"detail": "provider secret store is unavailable"}


def test_ocr_profile_activation_updates_persisted_and_live_configuration(monkeypatch, tmp_path):
    from oopsnote.api import main
    from oopsnote.api.routes import catalog

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    reference = vault.put("ocr-secret")
    profile = ProviderProfile(
        id="ocr", version=1, provider="openai-compatible", model="vision-model",
        base_url="https://ocr.example/v1", credential_ref=reference,
    )
    settings.upsert_provider_profile(profile)
    configured = {}
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)
    monkeypatch.setattr(catalog, "configure_ocr_vault", lambda store, ref, **kwargs: configured.update(
        store=store, reference=ref, **kwargs
    ))

    response = TestClient(main.app).post("/settings/ocr-profile", json={"profile_id": "ocr"})

    assert response.status_code == 200
    assert settings.get()["ocr_profile_id"] == "ocr"
    assert configured == {
        "store": vault,
        "reference": reference,
        "model": "vision-model",
        "endpoint": "https://ocr.example/v1",
    }


def test_provider_rotation_commits_metadata_as_a_new_nonsecret_version(monkeypatch, tmp_path):
    from oopsnote.api import main

    settings = AppSettingsStore(tmp_path / "settings.json")
    vault = MemorySecretStore()
    old_reference = vault.put("old-secret")
    old = ProviderProfile(
        id="primary", version=3, provider="deepseek", model="old-model",
        base_url="https://old.example/v1", credential_ref=old_reference,
    )
    settings.activate_provider_profile(old)
    monkeypatch.setattr(main, "APP_SETTINGS_STORE", settings)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
    monkeypatch.setattr(main, "get_secret_store", lambda: vault)

    with patch("oopsnote.api.routes.catalog.ProviderClientFactory.validate", return_value=None):
        response = TestClient(main.app).post(
            "/settings/provider-profiles/primary/secret",
            json={
                "secret": "new-secret",
                "provider": "openai-compatible",
                "model": "new-model",
                "base_url": "https://new.example/v1",
                "enabled": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "credential_ref" not in str(body)
    assert body["profile"]["version"] == 4
    assert body["profile"]["provider"] == "openai-compatible"
    assert body["profile"]["model"] == "new-model"
    assert body["profile"]["base_url"] == "https://new.example/v1"
    current = settings.provider_profiles()[0]
    assert vault.get(current.credential_ref) == "new-secret"
    assert not vault.has(old_reference)


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


def test_profile_activation_persists_profile_and_selection_atomically(tmp_path):
    store = AppSettingsStore(tmp_path / "settings.json")
    profile = ProviderProfile(
        id="primary", version=1, provider="deepseek", model="m1",
        base_url="https://provider.example", credential_ref="one",
    )

    store.activate_provider_profile(profile)

    assert store.provider_profiles() == [profile]
    assert store.get()["ai_provider_profile_id"] == "primary"


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


def test_legacy_model_and_ocr_import_create_profiles_without_persisting_secrets(tmp_path):
    from scripts.migrate_local_secrets import import_model_profile, import_ocr_profile

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

    model_profile = import_model_profile(
        auth,
        store=vault,
        settings=settings,
        profile_id="primary",
        provider="deepseek",
        model="chat-model",
        base_url="https://provider.example/v1",
    )
    ocr_profile = import_ocr_profile(
        extensions,
        store=vault,
        settings=settings,
        profile_id="ocr",
    )

    persisted = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "model-secret" not in persisted
    assert "ocr-secret" not in persisted
    assert vault.get(model_profile.credential_ref) == "model-secret"
    assert vault.get(ocr_profile.credential_ref) == "ocr-secret"
    assert settings.get()["ai_provider_profile_id"] == "primary"
    assert settings.get()["ocr_profile_id"] == "ocr"


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

    assert collect_unreferenced_profile_secrets(vault, [profile], run_store.list_all()) == 0
    assert vault.has(old_reference)
    run_store.finish(run.id, RunStatus.FAILED)

    assert collect_unreferenced_profile_secrets(vault, [profile], run_store.list_all()) == 1
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


def test_fresh_retry_keeps_failed_run_profile_snapshot(tmp_path):
    from oopsnote.ai.backends.langchain import LangChainRunner

    settings = AppSettingsStore(tmp_path / "settings.json")
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    old = ProviderProfile(
        id="p", version=1, provider="deepseek", model="old",
        base_url="https://provider.example", credential_ref="old-ref",
    )
    settings.activate_provider_profile(old)
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
        provider_profile_snapshot=old.model_dump(mode="json"),
    )
    run_store.finish(failed.id, RunStatus.FAILED)
    task_store.mark_status(task.id, TaskStatus.FAILED, "transient")
    settings.activate_provider_profile(old.model_copy(
        update={"version": 2, "model": "new", "credential_ref": "new-ref"}
    ))

    retry = runner.enqueue(task.id, retry_of=run_store.get(failed.id))

    assert retry.provider_profile_snapshot == old.model_dump(mode="json")
    assert retry.model == "old"


def test_provider_factory_disables_sdk_retries(monkeypatch):
    captured = {}

    class ChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=ChatModel))
    vault = MemorySecretStore()
    reference = vault.put("secret")
    profile = ProviderProfile(
        id="p", version=1, provider="deepseek", model="m",
        base_url="https://provider.example", credential_ref=reference,
    )

    ProviderClientFactory(vault).create_chat_model(profile)

    assert captured["api_key"] == "secret"
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60


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

    assert _configured_backend(None) == "langchain"
