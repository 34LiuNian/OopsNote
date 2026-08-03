"""Report the isolated LangChain production cohort without changing state.

The report deliberately does not infer quality, cancellation, duplicate-finalize
or provider cost gates from incomplete TaskRun fields. Those gates need explicit
evaluation evidence alongside the persisted run cohort.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oopsnote.core import RunStatus, RunStore, TaskRecord, TaskRun, TaskStore

TERMINAL = frozenset({
    RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT,
})
SYNTHETIC_SOURCES = ("langchain-benchmark-", "langchain-smoke-")


def _timestamp(run: TaskRun) -> datetime:
    return run.ended_at or run.heartbeat_at or run.queued_at


def _p95(values: list[int]) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def build_report(
    tasks: Iterable[TaskRecord],
    runs: Iterable[TaskRun],
    *,
    profile_id: Optional[str] = None,
    profile_version: Optional[int] = None,
    include_synthetic: bool = False,
) -> dict[str, Any]:
    tasks_by_id = {task.id: task for task in tasks}
    attempts: dict[str, list[TaskRun]] = defaultdict(list)
    for run in runs:
        snapshot = run.provider_profile_snapshot
        if run.backend != "langchain" or run.status not in TERMINAL or run.task_id not in tasks_by_id:
            continue
        if not isinstance(snapshot, dict):
            continue
        if profile_id is not None and snapshot.get("id") != profile_id:
            continue
        if profile_version is not None and snapshot.get("version") != profile_version:
            continue
        source = str(tasks_by_id[run.task_id].metadata.get("source", ""))
        if not include_synthetic and source.startswith(SYNTHETIC_SOURCES):
            continue
        attempts[run.task_id].append(run)

    outcomes: list[dict[str, Any]] = []
    for task_id, task_attempts in attempts.items():
        first = min(task_attempts, key=lambda run: run.queued_at)
        final = max(task_attempts, key=_timestamp)
        ended_at = _timestamp(final)
        outcomes.append({
            "task_id": task_id,
            "final_run_id": final.id,
            "status": final.status.value,
            "duration_ms": max(0, int((ended_at - first.queued_at).total_seconds() * 1000)),
            "attempt_count": len(task_attempts),
            "retry_count": max(run.retry_count for run in task_attempts),
            "cost": final.cost,
            "profile": {key: final.provider_profile_snapshot.get(key) for key in ("id", "version", "provider", "model")},
        })
    outcomes.sort(key=lambda item: item["task_id"])
    durations = [item["duration_ms"] for item in outcomes]
    total = len(outcomes)
    completed = sum(item["status"] == RunStatus.COMPLETED.value for item in outcomes)
    costs = [item["cost"] for item in outcomes]
    gates = {
        "at_least_30_real_tasks": total >= 30,
        "completion_rate_at_least_95_percent": total > 0 and completed / total >= 0.95,
        "no_lost_or_duplicate_finalize": None,
        "all_runs_cancellable": None,
        "quality_not_more_than_2pp_below_baseline": None,
        "p95_not_more_than_20_percent_above_baseline": None,
        "cost_threshold_approved_from_measured_usage": None,
    }
    return {
        "generated_at": datetime.now(timezone.utc),
        "filters": {"backend": "langchain", "profile_id": profile_id, "profile_version": profile_version, "include_synthetic": include_synthetic},
        "population": {"tasks": total, "completed": completed, "completion_rate": completed / total if total else None},
        "metrics": {
            "p50_duration_ms": round(statistics.median(durations)) if durations else None,
            "p95_duration_ms": _p95(durations),
            "total_cost": sum(float(cost or 0) for cost in costs),
            "cost_coverage": sum(cost is not None for cost in costs) / total if total else None,
        },
        "gates": gates,
        "all_gates_pass": all(value is True for value in gates.values()),
        "outcomes": outcomes,
    }


def markdown_report(report: dict[str, Any]) -> str:
    population = report["population"]
    metrics = report["metrics"]
    rate = population["completion_rate"]
    lines = [
        "# LangChain isolated evaluation report", "",
        "| metric | value |", "| --- | ---: |",
        f"| real terminal tasks | {population['tasks']} |",
        f"| completion rate | {'--' if rate is None else f'{rate * 100:.1f}%'} |",
        f"| P50 duration | {'--' if metrics['p50_duration_ms'] is None else f"{metrics['p50_duration_ms'] / 1000:.2f}s"} |",
        f"| P95 duration | {'--' if metrics['p95_duration_ms'] is None else f"{metrics['p95_duration_ms'] / 1000:.2f}s"} |",
        f"| total measured provider cost | {metrics['total_cost']:.6f} |",
        "", "| RustPi deletion gate | result |", "| --- | --- |",
    ]
    for name, value in report["gates"].items():
        lines.append(f"| {name.replace('_', ' ')} | {'pass' if value is True else 'not met' if value is False else 'not observed'} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", type=Path, default=ROOT / "storage")
    parser.add_argument("--profile-id")
    parser.add_argument("--profile-version", type=int)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    report = build_report(
        TaskStore(args.storage).list_all(),
        RunStore(args.storage / "runs").list_all(),
        profile_id=args.profile_id,
        profile_version=args.profile_version,
        include_synthetic=args.include_synthetic,
    )
    rendered = markdown_report(report)
    print(rendered)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (args.output_dir / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        (args.output_dir / f"{stamp}.md").write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
