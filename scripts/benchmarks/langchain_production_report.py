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
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oopsnote.core import RunStatus, RunStore, TaskRecord, TaskRun, TaskStore

TERMINAL = frozenset({
    RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT,
})
SYNTHETIC_SOURCES = (
    "langchain-benchmark-",
    "langchain-smoke-",
    "langchain-cancellation-",
)


class TaskEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    langchain_quality_pass: bool
    baseline_quality_pass: bool


class CancellationTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    cancellation_requested: bool
    reached_cancelled_terminal: bool
    terminal_state_preserved: bool


class CostApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    maximum_total_cost: float = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at: datetime


class EvaluationEvidence(BaseModel):
    """Versioned human-review evidence joined to authoritative persisted runs."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    profile_id: str = Field(min_length=1)
    profile_version: PositiveInt
    baseline_p95_ms: PositiveInt
    task_results: list[TaskEvaluation]
    cancellation_trials: list[CancellationTrial]
    cost_approval: CostApproval

    @model_validator(mode="after")
    def unique_references(self) -> "EvaluationEvidence":
        task_ids = [item.task_id for item in self.task_results]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task_results contains duplicate task_id values")
        run_ids = [item.run_id for item in self.cancellation_trials]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("cancellation_trials contains duplicate run_id values")
        return self


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
    evidence: EvaluationEvidence | None = None,
) -> dict[str, Any]:
    if evidence is not None:
        if profile_id is not None and profile_id != evidence.profile_id:
            raise ValueError("evidence profile_id does not match the report filter")
        if profile_version is not None and profile_version != evidence.profile_version:
            raise ValueError("evidence profile_version does not match the report filter")
        profile_id = evidence.profile_id
        profile_version = evidence.profile_version
    cohort_task_ids = (
        {item.task_id for item in evidence.task_results}
        if evidence is not None
        else None
    )
    tasks_by_id = {task.id: task for task in tasks}
    all_runs = list(runs)
    attempts: dict[str, list[TaskRun]] = defaultdict(list)
    matching_terminal_runs: dict[str, TaskRun] = {}
    for run in all_runs:
        snapshot = run.provider_profile_snapshot
        if run.backend != "langchain" or run.status not in TERMINAL or run.task_id not in tasks_by_id:
            continue
        if not isinstance(snapshot, dict):
            continue
        if profile_id is not None and snapshot.get("id") != profile_id:
            continue
        if profile_version is not None and snapshot.get("version") != profile_version:
            continue
        matching_terminal_runs[run.id] = run
        if cohort_task_ids is not None and run.task_id not in cohort_task_ids:
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
    evidence_task_ids = cohort_task_ids or set()
    observed_task_ids = {item["task_id"] for item in outcomes}
    exact_cohort = evidence is not None and observed_task_ids == evidence_task_ids
    quality_gate: bool | None = None
    integrity_gate: bool | None = None
    cancellation_gate: bool | None = None
    latency_gate: bool | None = None
    cost_gate: bool | None = None
    if evidence is not None:
        quality_count = sum(item.langchain_quality_pass for item in evidence.task_results)
        baseline_quality_count = sum(item.baseline_quality_pass for item in evidence.task_results)
        denominator = len(evidence.task_results)
        quality_gate = bool(
            exact_cohort
            and denominator
            and (baseline_quality_count - quality_count) / denominator <= 0.02
        )
        integrity_gate = bool(exact_cohort and all(
            sum(
                artifact.kind == "verifier_submission"
                for artifact in matching_terminal_runs[item["final_run_id"]].artifacts
            ) == (1 if item["status"] == RunStatus.COMPLETED.value else 0)
            for item in outcomes
        ))
        cancellation_gate = bool(
            evidence.cancellation_trials
            and all(
                item.cancellation_requested
                and item.reached_cancelled_terminal
                and item.terminal_state_preserved
                and item.run_id in matching_terminal_runs
                and matching_terminal_runs[item.run_id].status == RunStatus.CANCELLED
                for item in evidence.cancellation_trials
            )
        )
        measured_p95 = _p95(durations)
        latency_gate = bool(
            exact_cohort
            and measured_p95 is not None
            and measured_p95 <= evidence.baseline_p95_ms * 1.2
        )
        cost_coverage = sum(cost is not None for cost in costs) / total if total else None
        total_cost = sum(float(cost or 0) for cost in costs)
        cost_gate = bool(
            exact_cohort
            and cost_coverage == 1.0
            and evidence.cost_approval.approved
            and total_cost <= evidence.cost_approval.maximum_total_cost
        )
    gates = {
        "at_least_30_real_tasks": total >= 30 and (evidence is None or exact_cohort),
        "completion_rate_at_least_95_percent": total > 0 and completed / total >= 0.95,
        "no_lost_or_duplicate_finalize": integrity_gate,
        "all_runs_cancellable": cancellation_gate,
        "quality_not_more_than_2pp_below_baseline": quality_gate,
        "p95_not_more_than_20_percent_above_baseline": latency_gate,
        "cost_threshold_approved_from_measured_usage": cost_gate,
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
        "evidence": None if evidence is None else {
            "schema_version": evidence.schema_version,
            "profile_id": evidence.profile_id,
            "profile_version": evidence.profile_version,
            "cohort_matches_persisted_runs": exact_cohort,
            "baseline_p95_ms": evidence.baseline_p95_ms,
            "cost_currency": evidence.cost_approval.currency,
            "cost_limit": evidence.cost_approval.maximum_total_cost,
            "cost_approved_by": evidence.cost_approval.approved_by,
            "cost_approved_at": evidence.cost_approval.approved_at,
            "cancellation_trial_count": len(evidence.cancellation_trials),
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


def evidence_template(report: dict[str, Any], *, profile_id: str, profile_version: int) -> dict[str, Any]:
    """Create an intentionally incomplete review manifest for one persisted cohort."""
    return {
        "schema_version": 1,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "baseline_p95_ms": None,
        "task_results": [
            {
                "task_id": outcome["task_id"],
                "langchain_quality_pass": None,
                "baseline_quality_pass": None,
            }
            for outcome in report["outcomes"]
        ],
        "cancellation_trials": [],
        "cost_approval": {
            "approved": False,
            "maximum_total_cost": None,
            "currency": "",
            "approved_by": "",
            "approved_at": None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", type=Path, default=ROOT / "storage")
    parser.add_argument("--profile-id")
    parser.add_argument("--profile-version", type=int)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--write-evidence-template", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.evidence and args.write_evidence_template:
        parser.error("--evidence and --write-evidence-template are mutually exclusive")
    if args.write_evidence_template and (not args.profile_id or args.profile_version is None):
        parser.error("evidence templates require --profile-id and --profile-version")
    tasks = TaskStore(args.storage).list_all()
    runs = RunStore(args.storage / "runs").list_all()
    if args.write_evidence_template:
        preliminary = build_report(
            tasks,
            runs,
            profile_id=args.profile_id,
            profile_version=args.profile_version,
            include_synthetic=args.include_synthetic,
        )
        template = evidence_template(
            preliminary,
            profile_id=args.profile_id,
            profile_version=args.profile_version,
        )
        args.write_evidence_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_evidence_template.write_text(
            json.dumps(template, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote incomplete evidence template for {len(preliminary['outcomes'])} tasks")
        return 0
    evidence = (
        EvaluationEvidence.model_validate_json(args.evidence.read_text(encoding="utf-8"))
        if args.evidence
        else None
    )
    report = build_report(
        tasks,
        runs,
        profile_id=args.profile_id,
        profile_version=args.profile_version,
        include_synthetic=args.include_synthetic,
        evidence=evidence,
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
