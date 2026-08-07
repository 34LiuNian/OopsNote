"""Invariant tests for the multi-user control-plane foundation."""

from __future__ import annotations

import sqlite3
import threading
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from oopsnote.ai.work_items import ManagedWorkItem
from oopsnote.ai.langchain_tools import McpHttpToolClient
from oopsnote.api.context import RequestContext, activate_request_context, reset_request_context
from oopsnote.mcp.context import McpCapability, McpStores, activate_capability, reset_capability
from oopsnote.control import (
    ControlDatabase,
    ControlDatabaseError,
    QuotaError,
    QuotaService,
    WorkspaceRegistry,
)
from oopsnote.core import (
    Principal,
    RunPurpose,
    RunStatus,
    TaskCreateRequest,
    TaskStatus,
    UserRole,
    WorkspaceContext,
    WorkspaceId,
    WorkspaceStoreFactory,
)


def _registry(tmp_path) -> WorkspaceRegistry:
    return WorkspaceRegistry(
        ControlDatabase(tmp_path / "storage" / "control" / "app.sqlite"),
        tmp_path / "storage",
    )


def test_control_migrations_are_ordered_idempotent_and_enable_sqlite_guards(tmp_path):
    database = ControlDatabase(tmp_path / "storage" / "control" / "app.sqlite")

    assert database.migrate() == (1,)
    assert database.migrate() == (1,)

    with database.connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "schema_migrations",
        "workspaces",
        "quota_policies",
        "runs",
        "usage_reservations",
    } <= tables


def test_control_database_rejects_unknown_applied_migration(tmp_path):
    database = ControlDatabase(tmp_path / "app.sqlite")
    database.migrate()
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (99, 'future.sql', 'now')"
        )

    with pytest.raises(ControlDatabaseError, match="unknown migration"):
        database.migrate()


def test_registry_is_stable_for_one_user_and_physically_isolates_two_users(tmp_path):
    registry = _registry(tmp_path)
    alice = Principal("auth-alice", UserRole.USER)
    bob = Principal("auth-bob", UserRole.USER)

    alice_first = registry.get_or_create(alice)
    alice_again = registry.get_or_create(alice)
    bob_context = registry.get_or_create(bob)

    assert alice_first == alice_again
    assert alice_first.workspace_id != bob_context.workspace_id
    assert alice_first.root.parent == bob_context.root.parent
    assert alice_first.root != bob_context.root
    assert alice_first.root.is_dir()
    assert bob_context.root.is_dir()
    assert registry.require(alice) == alice_first

    with registry.database.connection() as connection:
        policies = connection.execute(
            "SELECT daily_success_limit, max_concurrent_runs FROM quota_policies ORDER BY workspace_id"
        ).fetchall()
    assert [(row[0], row[1]) for row in policies] == [(20, 1), (20, 1)]


def test_registry_concurrently_creates_only_one_mapping(tmp_path):
    registry = _registry(tmp_path)
    principal = Principal("auth-concurrent", UserRole.USER)
    barrier = threading.Barrier(8)
    workspace_ids: list[WorkspaceId] = []
    errors: list[Exception] = []

    def register() -> None:
        try:
            barrier.wait(timeout=2)
            workspace_ids.append(registry.get_or_create(principal).workspace_id)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    threads = [threading.Thread(target=register) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert len(set(workspace_ids)) == 1
    with registry.database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workspaces WHERE auth_user_id = ?",
            (principal.user_id,),
        ).fetchone()[0] == 1


def test_registry_provisions_and_reports_member_quota_without_exposing_content(tmp_path):
    registry = _registry(tmp_path)

    workspace = registry.provision(
        "auth-member",
        daily_success_limit=7,
        max_concurrent_runs=2,
    )
    summary = registry.quota_summary("auth-member")

    assert summary == {
        "workspace_id": str(workspace.workspace_id),
        "daily_success_limit": 7,
        "max_concurrent_runs": 2,
        "active_runs": 0,
        "used_units": 0,
        "usage_day_utc": datetime.now(timezone.utc).date().isoformat(),
    }
    assert registry.quota_summary("auth-missing") is None
    updated = registry.update_quota("auth-member", daily_success_limit=9)
    assert updated == {"daily_success_limit": 9, "max_concurrent_runs": 2}


def test_workspace_and_work_item_types_reject_ambiguous_identity(tmp_path):
    context = WorkspaceRegistry(
        ControlDatabase(tmp_path / "storage" / "control" / "app.sqlite"),
        tmp_path / "storage",
    ).get_or_create(Principal("auth-user", UserRole.USER))
    workspace_id = context.workspace_id
    item = ManagedWorkItem(
        workspace_id=workspace_id,
        task_id="task-1",
        run_id="run-1",
        purpose=RunPurpose.PROBLEM,
        quota_reservation_id="reservation-1",
    )

    assert context.root.name == str(workspace_id)
    assert item.workspace_id == workspace_id
    with pytest.raises(ValueError, match="canonical UUID"):
        WorkspaceId.parse("../other-user")
    with pytest.raises(ValueError, match="workspace context"):
        WorkspaceContext(workspace_id, tmp_path / "arbitrary")
    with pytest.raises(ValueError, match="role"):
        Principal("auth-user", "owner")
    with pytest.raises(ValueError, match="run_id"):
        ManagedWorkItem(workspace_id, "task-1", " ", RunPurpose.PROBLEM, "reservation-1")


def test_control_schema_enforces_workspace_foreign_keys(tmp_path):
    database = ControlDatabase(tmp_path / "app.sqlite")
    database.migrate()
    with database.connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO quota_policies(
                workspace_id, daily_success_limit, max_concurrent_runs, updated_at
            ) VALUES ('missing', 20, 1, 'now')
            """
        )


def test_workspace_store_factory_uses_independent_physical_roots(tmp_path):
    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first = factory.for_context(registry.get_or_create(Principal("auth-first", UserRole.USER)))
    second = factory.for_context(registry.get_or_create(Principal("auth-second", UserRole.USER)))

    assert first is factory.for_context(registry.require(Principal("auth-first", UserRole.USER)))
    assert first.task_store.base_dir != second.task_store.base_dir
    assert first.asset_store.base_dir != second.asset_store.base_dir
    assert first.run_store.base_dir != second.run_store.base_dir
    assert first.tag_store.user_path != second.tag_store.user_path
    assert first.paper_draft_store.base_dir != second.paper_draft_store.base_dir


def test_request_context_exposes_only_the_registered_workspace_stores(tmp_path):
    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first_context = registry.get_or_create(Principal("auth-context-a", UserRole.USER))
    second_context = registry.get_or_create(Principal("auth-context-b", UserRole.USER))
    from oopsnote.api import main

    first_token = activate_request_context(
        RequestContext(
            Principal("auth-context-a", UserRole.USER),
            first_context,
            factory.for_context(first_context),
        )
    )
    try:
        first_api = main.request_api()
        assert first_api.TASK_STORE.base_dir == first_context.root / "tasks"
        assert first_api.ASSET_STORE.base_dir == first_context.root / "assets"
    finally:
        reset_request_context(first_token)

    second_token = activate_request_context(
        RequestContext(
            Principal("auth-context-b", UserRole.USER),
            second_context,
            factory.for_context(second_context),
        )
    )
    try:
        second_api = main.request_api()
        assert second_api.TASK_STORE.base_dir == second_context.root / "tasks"
        assert second_api.TASK_STORE.base_dir != first_context.root / "tasks"
    finally:
        reset_request_context(second_token)


def test_quota_admission_is_atomic_idempotent_and_settles_terminal_runs(tmp_path):
    registry = _registry(tmp_path)
    principal = Principal("auth-quota", UserRole.USER)
    workspace = registry.get_or_create(principal).workspace_id
    service = QuotaService(registry.database)
    admitted = service.admit_run(
        workspace,
        task_id="task-1",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="task-1:problem",
        run_id="run-1",
    )
    repeated = service.admit_run(
        workspace,
        task_id="task-1",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="task-1:problem",
        run_id="run-different",
    )

    assert admitted.created is True
    assert repeated.created is False
    assert repeated.run_id == admitted.run_id
    with pytest.raises(QuotaError, match="Concurrent"):
        service.admit_run(
            workspace,
            task_id="task-2",
            purpose=RunPurpose.PROBLEM,
            idempotency_key="task-2:problem",
        )

    assert service.settle_run(workspace, admitted.run_id, status="failed") == "failed"
    next_run = service.admit_run(
        workspace,
        task_id="task-2",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="task-2:problem",
    )
    assert next_run.created is True
    assert service.settle_run(workspace, next_run.run_id, status="completed") == "completed"
    with registry.database.connection() as connection:
        states = connection.execute(
            "SELECT state FROM usage_reservations ORDER BY id"
        ).fetchall()
    assert {row[0] for row in states} == {"released", "consumed"}


def test_mcp_capability_cannot_resolve_another_workspace_task(tmp_path):
    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first_context = registry.get_or_create(Principal("auth-mcp-a", UserRole.USER))
    second_context = registry.get_or_create(Principal("auth-mcp-b", UserRole.USER))
    first = factory.for_context(first_context)
    second = factory.for_context(second_context)
    first_task = first.task_store.create(TaskCreateRequest(subject="math"))
    from oopsnote.mcp import server

    capability = McpCapability(
        workspace_id=second_context.workspace_id,
        stores=McpStores(
            task_store=second.task_store,
            tag_store=second.tag_store,
            asset_store=second.asset_store,
            run_store=second.run_store,
        ),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    token = activate_capability(capability)
    try:
        assert server._stores().task_store.base_dir == second_context.root / "tasks"
        with pytest.raises(KeyError):
            server._stores().task_store.get(first_task.id)
    finally:
        reset_capability(token)


def test_mcp_runtime_issues_distinct_workspace_tokens(tmp_path):
    from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime

    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first_context = registry.get_or_create(Principal("auth-token-a", UserRole.USER))
    second_context = registry.get_or_create(Principal("auth-token-b", UserRole.USER))
    runtime = SharedMcpHttpRuntime()
    runtime.start()
    try:
        first = runtime.environment_for(
            first_context.workspace_id,
            factory.for_context(first_context),
        )
        second = runtime.environment_for(
            second_context.workspace_id,
            factory.for_context(second_context),
        )
        assert first["OOPSNOTE_MCP_TOKEN"] != second["OOPSNOTE_MCP_TOKEN"]
        assert runtime.capability_for_token(
            first["OOPSNOTE_MCP_TOKEN"]
        ).workspace_id == first_context.workspace_id
        assert runtime.capability_for_token(
            second["OOPSNOTE_MCP_TOKEN"]
        ).workspace_id == second_context.workspace_id
    finally:
        runtime.shutdown()


def test_mcp_http_token_enforces_workspace_store_selection(tmp_path):
    from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime

    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first_context = registry.get_or_create(Principal("auth-http-mcp-a", UserRole.USER))
    second_context = registry.get_or_create(Principal("auth-http-mcp-b", UserRole.USER))
    first = factory.for_context(first_context)
    second = factory.for_context(second_context)
    task = first.task_store.create(TaskCreateRequest(subject="math"))
    run = first.run_store.create(task.id, backend="langchain")
    first.task_store.update(
        task.id,
        status=TaskStatus.PROCESSING,
        active_run_id=run.id,
    )
    runtime = SharedMcpHttpRuntime()
    runtime.start()
    try:
        first_env = runtime.environment_for(first_context.workspace_id, first)
        second_env = runtime.environment_for(second_context.workspace_id, second)
        first_client = McpHttpToolClient(
            first_env["OOPSNOTE_MCP_URL"],
            first_env["OOPSNOTE_MCP_TOKEN"],
        )
        second_client = McpHttpToolClient(
            second_env["OOPSNOTE_MCP_URL"],
            second_env["OOPSNOTE_MCP_TOKEN"],
        )
        result = asyncio.run(
            first_client.call("get_task", {"task_id": task.id, "run_id": run.id})
        )
        assert result["isError"] is False
        with pytest.raises(RuntimeError):
            asyncio.run(
                second_client.call("get_task", {"task_id": task.id, "run_id": run.id})
            )
    finally:
        runtime.shutdown()


def test_workspace_runner_pool_is_scoped_and_reuses_only_within_workspace(tmp_path):
    from oopsnote.api import main

    registry = _registry(tmp_path)
    factory = WorkspaceStoreFactory()
    first_context = registry.get_or_create(Principal("auth-runner-a", UserRole.USER))
    second_context = registry.get_or_create(Principal("auth-runner-b", UserRole.USER))
    first_stores = factory.for_context(first_context)
    second_stores = factory.for_context(second_context)
    pool = main.WorkspaceRunnerPool()
    try:
        first = pool.get(first_context.workspace_id, first_stores, "hermes")
        repeated = pool.get(first_context.workspace_id, first_stores, "hermes")
        second = pool.get(second_context.workspace_id, second_stores, "hermes")
        assert repeated is first
        assert second is not first
        assert first.task_store.base_dir == first_context.root / "tasks"
        assert second.task_store.base_dir == second_context.root / "tasks"
    finally:
        pool.shutdown()


def test_workspace_run_store_enforces_concurrency_and_releases_failed_usage(tmp_path):
    registry = _registry(tmp_path)
    context = registry.get_or_create(Principal("auth-run-quota", UserRole.USER))
    stores = WorkspaceStoreFactory().for_context(context)
    first = stores.run_store.create("task-1", backend="hermes")

    with pytest.raises(QuotaError, match="Concurrent"):
        stores.run_store.create("task-2", backend="hermes")

    stores.run_store.finish(first.id, RunStatus.FAILED, error_code="provider_unavailable")
    second = stores.run_store.create("task-2", backend="hermes")
    assert second.quota_reservation_id != first.quota_reservation_id


def test_workspace_retry_reuses_one_reservation_and_consumes_it_once(tmp_path):
    registry = _registry(tmp_path)
    context = registry.get_or_create(Principal("auth-run-retry", UserRole.USER))
    stores = WorkspaceStoreFactory().for_context(context)
    first = stores.run_store.create("task-1", backend="hermes")
    stores.run_store.finish(first.id, RunStatus.FAILED, error_code="provider_unavailable")
    retry = stores.run_store.create("task-1", backend="hermes", retry_of=first)

    assert retry.quota_reservation_id == first.quota_reservation_id
    stores.run_store.finish(retry.id, RunStatus.COMPLETED)
    with registry.database.connection() as connection:
        reservation = connection.execute(
            "SELECT state, units FROM usage_reservations WHERE id = ?",
            (first.quota_reservation_id,),
        ).fetchone()
        control_runs = connection.execute(
            "SELECT id, retry_of FROM runs WHERE quota_reservation_id = ? ORDER BY queued_at",
            (first.quota_reservation_id,),
        ).fetchall()
    assert tuple(reservation) == ("consumed", 1)
    assert len(control_runs) == 2
    assert control_runs[1]["retry_of"] == first.id


def test_retry_rechecks_concurrency_and_preserves_the_original_operation(tmp_path):
    registry = _registry(tmp_path)
    context = registry.get_or_create(Principal("auth-retry-guards", UserRole.USER))
    service = QuotaService(registry.database)
    first = service.admit_run(
        context.workspace_id,
        task_id="task-1",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="first",
        run_id="run-1",
    )
    service.settle_run(context.workspace_id, first.run_id, status="failed")

    with pytest.raises(QuotaError, match="preserve task and purpose"):
        service.admit_retry(
            context.workspace_id,
            previous_run_id=first.run_id,
            task_id="task-2",
            purpose=RunPurpose.PROBLEM,
            run_id="run-invalid",
        )

    active = service.admit_run(
        context.workspace_id,
        task_id="task-2",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="active",
        run_id="run-active",
    )
    with pytest.raises(QuotaError, match="Concurrent"):
        service.admit_retry(
            context.workspace_id,
            previous_run_id=first.run_id,
            task_id="task-1",
            purpose=RunPurpose.PROBLEM,
            run_id="run-retry",
        )
    service.settle_run(context.workspace_id, active.run_id, status="failed")


def test_retry_moves_released_usage_to_the_retry_day_and_rechecks_daily_limit(tmp_path):
    registry = _registry(tmp_path)
    context = registry.get_or_create(Principal("auth-retry-day", UserRole.USER))
    service = QuotaService(registry.database)
    day_one = datetime(2026, 8, 6, 23, 59, tzinfo=timezone.utc)
    day_two = datetime(2026, 8, 7, 0, 1, tzinfo=timezone.utc)
    first = service.admit_run(
        context.workspace_id,
        task_id="task-1",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="first",
        run_id="run-1",
        now=day_one,
    )
    service.settle_run(context.workspace_id, first.run_id, status="failed", now=day_one)
    retry = service.admit_retry(
        context.workspace_id,
        previous_run_id=first.run_id,
        task_id="task-1",
        purpose=RunPurpose.PROBLEM,
        run_id="run-retry",
        now=day_two,
    )
    with registry.database.connection() as connection:
        usage_day = connection.execute(
            "SELECT usage_day_utc FROM usage_reservations WHERE id = ?",
            (retry.reservation_id,),
        ).fetchone()[0]
    assert usage_day == "2026-08-07"

    service.settle_run(context.workspace_id, retry.run_id, status="completed", now=day_two)
    registry.update_quota("auth-retry-day", daily_success_limit=1)
    second = service.admit_run(
        context.workspace_id,
        task_id="task-2",
        purpose=RunPurpose.PROBLEM,
        idempotency_key="second",
        run_id="run-2",
        now=day_one,
    )
    service.settle_run(context.workspace_id, second.run_id, status="failed", now=day_one)
    with pytest.raises(QuotaError, match="Daily"):
        service.admit_retry(
            context.workspace_id,
            previous_run_id=second.run_id,
            task_id="task-2",
            purpose=RunPurpose.PROBLEM,
            run_id="run-2-retry",
            now=day_two,
        )


def test_consumed_daily_limit_blocks_the_next_workspace_run(tmp_path):
    registry = _registry(tmp_path)
    context = registry.get_or_create(Principal("auth-run-daily", UserRole.USER))
    with registry.database.connection() as connection:
        connection.execute(
            "UPDATE quota_policies SET daily_success_limit = 1 WHERE workspace_id = ?",
            (str(context.workspace_id),),
        )
    stores = WorkspaceStoreFactory().for_context(context)
    first = stores.run_store.create("task-1", backend="hermes")
    stores.run_store.finish(first.id, RunStatus.COMPLETED)

    with pytest.raises(QuotaError, match="Daily"):
        stores.run_store.create("task-2", backend="hermes")
