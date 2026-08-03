"""Report the observed Pi-rust production cohort without changing stored state.

The Hermes-retirement gate counts one final terminal outcome per task. Retries
remain part of that task's end-to-end duration, rather than inflating the
success denominator. Historic missing measurements stay ``None`` and are
reported as incomplete coverage.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oopsnote.core import RunStatus, RunStore, TaskRecord, TaskRun, TaskStore

REPORT_ROOT = ROOT / "storage" / "pi-production-report"
TERMINAL = frozenset({
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
})
SYNTHETIC_SOURCES = ("pi-benchmark-", "pi-smoke-")


def _timestamp(run: TaskRun) -> datetime:
    return run.ended_at or run.heartbeat_at or run.queued_at


def _nearest_rank(values: list[int]) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _coverage(values: Iterable[object | None], total: int) -> Optional[float]:
    return sum(value is not None for value in values) / total if total else None


def build_report(
    tasks: Iterable[TaskRecord],
    runs: Iterable[TaskRun],
    *,
    runtime: str = "pi-rust",
    prompt_version: Optional[str] = None,
    include_synthetic: bool = False,
) -> dict[str, Any]:
    """Build a truthful cohort report from persisted task/run records."""
    tasks_by_id = {task.id: task for task in tasks}
    selected_runs: list[TaskRun] = []
    orphaned_runs: list[TaskRun] = []
    for run in runs:
        task = tasks_by_id.get(run.task_id)
        if (
            run.runtime_kind == runtime
            and run.status in TERMINAL
            and (prompt_version is None or run.prompt_version == prompt_version)
        ):
            if task is None:
                # Run files are retained for forensics after a task is deleted.
                # They are attempt evidence, not task outcomes, and cannot enter
                # a task-level production denominator.
                orphaned_runs.append(run)
                continue
            source = str(task.metadata.get("source", ""))
            if include_synthetic or not source.startswith(SYNTHETIC_SOURCES):
                selected_runs.append(run)
    attempts_by_task: dict[str, list[TaskRun]] = defaultdict(list)
    for run in selected_runs:
        attempts_by_task[run.task_id].append(run)

    outcomes: list[dict[str, Any]] = []
    for task_id, attempts in attempts_by_task.items():
        final = max(attempts, key=_timestamp)
        first = min(attempts, key=lambda run: run.queued_at)
        ended_at = final.ended_at or final.heartbeat_at
        duration_ms = max(0, int((ended_at - first.queued_at).total_seconds() * 1000))
        task = tasks_by_id.get(task_id)
        outcomes.append({
            "task_id": task_id,
            "final_run_id": final.id,
            "status": final.status.value,
            "queued_at": first.queued_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "attempt_count": len(attempts),
            "retry_count": max(run.retry_count for run in attempts),
            "peak_memory_bytes": final.peak_memory_bytes,
            "cost": final.cost,
            "revision_count": task.revision_count if task else None,
        })

    outcomes.sort(key=lambda outcome: outcome["queued_at"])
    total = len(outcomes)
    successful = sum(outcome["status"] == RunStatus.COMPLETED.value for outcome in outcomes)
    durations = [int(outcome["duration_ms"]) for outcome in outcomes]
    started = outcomes[0]["queued_at"] if outcomes else None
    ended = max((outcome["ended_at"] for outcome in outcomes), default=None)
    observation_seconds = (ended - started).total_seconds() if started and ended else 0
    observation_days = observation_seconds / 86400
    success_rate = successful / total if total else None
    metrics = {
        "p50_duration_ms": round(statistics.median(durations)) if durations else None,
        "p95_duration_ms": _nearest_rank(durations),
        "total_cost": sum(float(outcome["cost"] or 0) for outcome in outcomes),
        "memory_coverage": _coverage((outcome["peak_memory_bytes"] for outcome in outcomes), total),
        "cost_coverage": _coverage((outcome["cost"] for outcome in outcomes), total),
        "revision_coverage": _coverage((outcome["revision_count"] for outcome in outcomes), total),
    }
    retirement_gates = {
        "at_least_30_tasks": total >= 30,
        "at_least_7_days": observation_seconds >= 7 * 86400,
        "success_rate_at_least_95_percent": success_rate is not None and success_rate >= 0.95,
        # These require a comparable Hermes quality/latency baseline and a
        # recorded fault-injection run. This report has no authority to infer
        # either from production task records.
        "quality_not_more_than_2pp_below_hermes": None,
        "p95_not_more_than_20_percent_above_hermes": None,
        "fault_injection_passed": None,
    }
    orphaned_by_status = Counter(run.status.value for run in orphaned_runs)
    orphaned_by_result_code = Counter(
        run.error_code or run.status.value for run in orphaned_runs
    )
    return {
        "generated_at": datetime.now(timezone.utc),
        "filters": {
            "runtime": runtime,
            "prompt_version": prompt_version,
            "include_synthetic": include_synthetic,
        },
        "population": {
            "tasks": total,
            "successful_tasks": successful,
            "success_rate": success_rate,
            "observation_days": observation_days,
            "first_queued_at": started,
            "last_ended_at": ended,
        },
        "metrics": metrics,
        "orphaned_terminal_runs": {
            "count": len(orphaned_runs),
            "by_status": dict(sorted(orphaned_by_status.items())),
            "by_result_code": dict(sorted(orphaned_by_result_code.items())),
            "run_ids": [run.id for run in sorted(orphaned_runs, key=_timestamp)],
        },
        "retirement_gates": retirement_gates,
        "all_retirement_gates_pass": all(value is True for value in retirement_gates.values()),
        "outcomes": outcomes,
    }


def _percent(value: Optional[float]) -> str:
    return "--" if value is None else f"{value * 100:.1f}%"


def _ms(value: Optional[int]) -> str:
    return "--" if value is None else f"{value / 1000:.2f}s"


def markdown_report(report: dict[str, Any]) -> str:
    population = report["population"]
    metrics = report["metrics"]
    orphaned = report["orphaned_terminal_runs"]
    lines = [
        "# Pi-rust production observation",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| terminal tasks | {population['tasks']} |",
        f"| successful tasks | {population['successful_tasks']} |",
        f"| success rate | {_percent(population['success_rate'])} |",
        f"| observation window | {population['observation_days']:.2f} days |",
        f"| P50 end-to-end duration | {_ms(metrics['p50_duration_ms'])} |",
        f"| P95 end-to-end duration (nearest rank) | {_ms(metrics['p95_duration_ms'])} |",
        f"| memory coverage | {_percent(metrics['memory_coverage'])} |",
        f"| cost coverage | {_percent(metrics['cost_coverage'])} |",
        f"| revision coverage | {_percent(metrics['revision_coverage'])} |",
        f"| observed total cost | {metrics['total_cost']:.6f} |",
        f"| orphaned terminal runs excluded from task cohort | {orphaned['count']} |",
        "",
        "| Hermes retirement gate | result |",
        "| --- | --- |",
    ]
    for name, passed in report["retirement_gates"].items():
        result = "pass" if passed is True else "not met" if passed is False else "not observed"
        lines.append(f"| {name.replace('_', ' ')} | {result} |")
    summary = "pass" if report["all_retirement_gates_pass"] else "not met"
    lines.append(f"| all retirement gates | {summary} |")
    if orphaned["count"]:
        lines.extend([
            "",
            "Orphaned runs are retained as forensic attempt evidence and do not "
            "contribute to task-level success or latency metrics.",
            "",
            "| orphaned result code | count |",
            "| --- | ---: |",
        ])
        for result_code, count in orphaned["by_result_code"].items():
            lines.append(f"| {result_code} | {count} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", default="pi-rust")
    parser.add_argument("--prompt-version")
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=REPORT_ROOT)
    args = parser.parse_args()
    storage = ROOT / "storage"
    report = build_report(
        TaskStore(storage).list_all(),
        RunStore(storage / "runs").list_all(),
        runtime=args.runtime,
        prompt_version=args.prompt_version,
        include_synthetic=args.include_synthetic,
    )
    rendered = markdown_report(report)
    print(rendered)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (args.output_dir / f"{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / f"{stamp}.md").write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["all_retirement_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
