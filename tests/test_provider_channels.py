from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from oopsnote.ai.providers import (
    ChannelModel,
    LangChainModelPolicy,
    ProviderCapabilities,
    ProviderChannel,
    ProviderClientFactory,
    StageModelSelection,
)
from oopsnote.ai.secrets import MemorySecretStore
from oopsnote.core import AppSettingsStore
from oopsnote.core import RunStatus, RunStore, TaskCreateRequest, TaskStore


def channel(vault: MemorySecretStore) -> ProviderChannel:
    return ProviderChannel(
        id="gateway",
        version=1,
        display_name="Gateway",
        provider="openai-compatible",
        base_url="https://gateway.example/v1",
        credential_ref=vault.put("secret"),
        models=(ChannelModel(
            id="text", source="DeepSeek", enabled=True,
            capability=ProviderCapabilities(tool_calling=True, vision=True),
        ),),
        created_at=datetime.now(timezone.utc),
    )


def test_discovery_groups_by_provider_source_and_closes_unknown_capabilities():
    vault = MemorySecretStore()
    configured = channel(vault)
    response = type("Response", (), {
        "raise_for_status": lambda self: None,
        "json": lambda self: {"data": [{"id": "deepseek-chat", "owned_by": "DeepSeek"}, {"id": "other", "owned_by": "Other"}]},
    })()
    with patch("httpx.get", return_value=response):
        models = ProviderClientFactory(vault).discover_models(configured)
    assert [(item.id, item.source) for item in models] == [("deepseek-chat", "DeepSeek"), ("other", "Other")]
    assert all(not item.enabled for item in models)
    assert all(item.capability == ProviderCapabilities() for item in models)


def test_policy_and_channel_are_persisted_as_one_authoritative_settings_shape(tmp_path: Path):
    vault = MemorySecretStore()
    store = AppSettingsStore(tmp_path / "settings.json")
    configured = channel(vault)
    store.upsert_provider_channel(configured)
    selection = StageModelSelection(channel_id=configured.id, model_id="text")
    policy = LangChainModelPolicy(version=1, vision=selection, agent=selection, review=selection)
    store.set_langchain_model_policy(policy)
    assert store.provider_channels() == [configured]
    assert store.langchain_model_policy() == policy
    assert "provider_profiles" not in store.get()


def test_channel_mutation_atomically_clears_a_policy_that_is_no_longer_runnable(tmp_path: Path):
    vault = MemorySecretStore()
    store = AppSettingsStore(tmp_path / "settings.json")
    configured = channel(vault)
    store.upsert_provider_channel(configured)
    selection = StageModelSelection(channel_id=configured.id, model_id="text")
    store.set_langchain_model_policy(LangChainModelPolicy(
        version=1, vision=selection, agent=selection, review=selection,
    ))

    store.upsert_provider_channel(configured.model_copy(update={
        "version": 2,
        "models": (configured.models[0].model_copy(update={"enabled": False}),),
    }))

    assert store.langchain_model_policy() is None


def test_store_rejects_persisting_a_policy_with_missing_capability(tmp_path: Path):
    vault = MemorySecretStore()
    store = AppSettingsStore(tmp_path / "settings.json")
    configured = channel(vault).model_copy(update={
        "models": (ChannelModel(id="text", source="DeepSeek", enabled=True),),
    })
    store.upsert_provider_channel(configured)
    selection = StageModelSelection(channel_id=configured.id, model_id="text")

    with pytest.raises(ValueError, match="unavailable channel or model"):
        store.set_langchain_model_policy(LangChainModelPolicy(
            version=1, vision=selection, agent=selection, review=selection,
        ))


def test_retiring_legacy_profile_shape_returns_only_opaque_references(tmp_path: Path):
    store = AppSettingsStore(tmp_path / "settings.json")
    store.update({
        "provider_profiles": [
            {"id": "old", "credential_ref": "opaque-old", "version": 1},
            {"id": "without-secret", "version": 1},
        ],
        "ai_provider_profile_id": "old",
    })

    assert store.retire_legacy_provider_secrets() == ["opaque-old"]
    assert "provider_profiles" not in store.get()
    assert "ai_provider_profile_id" not in store.get()


def test_secret_collection_retains_current_channel_reference(tmp_path: Path):
    vault = MemorySecretStore()
    store = AppSettingsStore(tmp_path / "settings.json")
    configured = channel(vault)
    store.upsert_provider_channel(configured)
    tasks = TaskStore(tmp_path / "tasks")
    runs = RunStore(tmp_path / "runs")
    task = tasks.create(TaskCreateRequest(subject="math"))
    run = runs.create(
        task.id,
        backend="langchain",
        provider="openai-compatible",
        model="text",
        provider_profile_snapshot={"agent": {"credential_ref": configured.credential_ref}},
    )
    runs.finish(run.id, RunStatus.COMPLETED)
    from oopsnote.ai.providers import collect_unreferenced_channel_secrets

    assert collect_unreferenced_channel_secrets(vault, store.provider_channels(), runs.list_all()) == 0
    assert vault.has(configured.credential_ref)


def test_secret_collection_finds_nested_stage_snapshot_references(tmp_path: Path):
    vault = MemorySecretStore()
    stale_ref = vault.put("stale")
    tasks = TaskStore(tmp_path / "tasks")
    runs = RunStore(tmp_path / "runs")
    task = tasks.create(TaskCreateRequest(subject="math"))
    run = runs.create(
        task.id,
        backend="langchain",
        provider_profile_snapshot={"vision": {"credential_ref": stale_ref}, "agent": {"credential_ref": stale_ref}},
    )
    runs.finish(run.id, RunStatus.COMPLETED)
    from oopsnote.ai.providers import collect_unreferenced_channel_secrets

    assert collect_unreferenced_channel_secrets(vault, [], runs.list_all()) == 1
    assert not vault.has(stale_ref)


def test_langchain_admission_freezes_all_three_stage_models_and_rejects_closed_capability(tmp_path: Path):
    from oopsnote.ai.backends.langchain import LangChainRunner

    vault = MemorySecretStore()
    settings = AppSettingsStore(tmp_path / "settings.json")
    configured = channel(vault).model_copy(update={
        "models": (
            ChannelModel(id="vision", source="Gateway", enabled=True, capability=ProviderCapabilities(vision=True)),
            ChannelModel(id="agent", source="Gateway", enabled=True, capability=ProviderCapabilities(tool_calling=True)),
            ChannelModel(id="review", source="Gateway", enabled=True, capability=ProviderCapabilities(tool_calling=True)),
        )
    })
    settings.upsert_provider_channel(configured)
    settings.set_langchain_model_policy(LangChainModelPolicy(
        version=1,
        vision=StageModelSelection(channel_id=configured.id, model_id="vision"),
        agent=StageModelSelection(channel_id=configured.id, model_id="agent"),
        review=StageModelSelection(channel_id=configured.id, model_id="review"),
    ))
    tasks = TaskStore(tmp_path / "tasks")
    runs = RunStore(tmp_path / "runs")
    runner = LangChainRunner(
        project_root=Path(__file__).resolve().parents[1],
        task_store=tasks,
        run_store=runs,
        settings_store=settings,
        provider_factory=lambda: type("Factory", (), {"secret_store": vault})(),
        tool_client_factory=lambda: None,
        timeout_seconds=10,
        poll_seconds=0.01,
        heartbeat_seconds=0.05,
    )
    task = tasks.create(TaskCreateRequest(subject="math"))
    metadata = runner._run_metadata(task.id)
    assert set(metadata["provider_profile_snapshot"]) == {"policy_version", "vision", "agent", "review"}
    assert metadata["provider_profile_snapshot"]["vision"]["model"] == "vision"
    closed = configured.model_copy(update={
        "version": 2,
        "models": tuple(item.model_copy(update={"capability": ProviderCapabilities()}) for item in configured.models),
    })
    settings.upsert_provider_channel(closed)
    assert settings.langchain_model_policy() is None
    with pytest.raises(RuntimeError, match="no global LangChain model policy"):
        runner._run_metadata(task.id)
