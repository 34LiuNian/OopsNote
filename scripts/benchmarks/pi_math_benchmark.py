"""Run sequential Pi OCR-to-finalize benchmarks against existing math crops."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oopsnote.ai import PiRpcBackend, PiRpcRunner
from oopsnote.core import AssetStore, RunStore, TaskCreateRequest, TaskStore
from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime
from scripts.benchmarks.pi_math_cases import (
    MATH_BENCHMARK_CASES,
    benchmark_answers_match,
)

ASSET_ROOT = ROOT / "storage" / "assets"
REPORT_ROOT = ROOT / "storage" / "pi-benchmark"


def find_asset(pattern: str) -> Path:
    matches = sorted(ASSET_ROOT.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one asset for {pattern}, found {len(matches)}")
    return matches[0]


def preflight(backend: PiRpcBackend) -> list[str]:
    issues: list[str] = []
    config_dir = ROOT / (".pi" if backend.runtime_kind == "pi-rust" else f".{backend.runtime_kind}")
    extension_config = config_dir / "extensions.json"
    adapter_dir = ROOT / ".pi" / "node_modules" / "pi-mcp-adapter"
    if not extension_config.exists():
        issues.append(f"missing {config_dir.name}/extensions.json")
    else:
        try:
            ocr = json.loads(extension_config.read_text(encoding="utf-8")).get("ocr_image", {})
            if not ocr.get("dashscope_api_key"):
                issues.append(f"missing DashScope key in {config_dir.name}/extensions.json")
            if not ocr.get("model"):
                issues.append(f"missing OCR model in {config_dir.name}/extensions.json")
        except (OSError, json.JSONDecodeError):
            issues.append(f"invalid {config_dir.name}/extensions.json")
    if backend.runtime_kind == "pi" and not adapter_dir.exists():
        issues.append("missing .pi/node_modules/pi-mcp-adapter; run npm install in .pi")
    executable = backend.command[0]
    if not (Path(executable).exists() or shutil.which(executable)):
        issues.append(f"{backend.runtime_kind.upper()} launcher not found: {executable}")
    return issues


def ms(value: int | None) -> str:
    return f"{value / 1000:.2f}s" if value is not None else "--"


def stage_durations(run) -> dict[str, int | None]:
    return {entry.stage.value: entry.latency_ms for entry in run.stage_runs}


def markdown_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| case | expected | answer | result | OCR | solve | verify | tag | total | input/output/cache | cost |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        stages = row["stages"]
        token_pair = (
            f"{row['input_tokens'] or 0}/{row['output_tokens'] or 0}/{row.get('cache_tokens') or 0}"
        )
        cost = "--" if row["cost"] is None else f"{row['cost']:.6f}"
        lines.append(
            f"| {row['case']} | {row['expected']} | {row['answer'] or '--'} | {row['status']} | "
            f"{ms(stages.get('ocr'))} | {ms(stages.get('solving'))} | {ms(stages.get('verifying'))} | "
            f"{ms(stages.get('tagging'))} | {ms(row['duration_ms'])} | {token_pair} | {cost} |"
        )
    return "\n".join(lines)


def summary_table(rows: list[dict[str, object]]) -> str:
    durations = [int(row["duration_ms"]) for row in rows if row.get("duration_ms") is not None]
    sorted_durations = sorted(durations)
    p95 = (
        sorted_durations[math.ceil(len(sorted_durations) * 0.95) - 1] if sorted_durations else None
    )
    stage_averages: dict[str, str] = {}
    for stage in ("ocr", "solving", "verifying", "tagging"):
        values = [
            int(stages[stage])
            for row in rows
            if isinstance((stages := row["stages"]), dict) and stages.get(stage) is not None
        ]
        stage_averages[stage] = ms(round(statistics.mean(values))) if values else "--"
    completed = sum(row["status"] == "completed" for row in rows)
    correct = sum(
        row["status"] == "completed"
        and benchmark_answers_match(str(row["answer"]), str(row["expected"]))
        for row in rows
    )
    total_cost = sum(float(row["cost"] or 0) for row in rows)
    lines = [
        "| metric | value |",
        "| --- | ---: |",
        f"| completed / total | {completed}/{len(rows)} |",
        f"| correct / total | {correct}/{len(rows)} |",
        f"| total duration | {ms(sum(durations))} |",
        f"| mean duration | {ms(round(statistics.mean(durations))) if durations else '--'} |",
        f"| P50 duration | {ms(round(statistics.median(durations))) if durations else '--'} |",
        f"| P95 duration (nearest rank) | {ms(p95)} |",
        f"| mean OCR / solve / verify / tag | {stage_averages['ocr']} / {stage_averages['solving']} / {stage_averages['verifying']} / {stage_averages['tagging']} |",
        f"| input / output / cache tokens | {sum(int(row['input_tokens'] or 0) for row in rows)} / {sum(int(row['output_tokens'] or 0) for row in rows)} / {sum(int(row.get('cache_tokens') or 0) for row in rows)} |",
        f"| total cost | {total_cost:.6f} |",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=("pi", "pi-rust"), default="pi-rust")
    args = parser.parse_args()
    backend = PiRpcBackend(ROOT, runtime=args.runtime)
    issues = preflight(backend)
    if issues:
        print("Benchmark preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        return 2

    storage = ROOT / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    _assets = AssetStore(ASSET_ROOT)
    runner = PiRpcRunner(
        backend=backend,
        project_root=ROOT,
        task_store=task_store,
        run_store=run_store,
    )
    mcp_runtime = SharedMcpHttpRuntime()
    runner.set_child_environment(mcp_runtime.start())
    rows: list[dict[str, object]] = []
    try:
        for case in MATH_BENCHMARK_CASES:
            source = find_asset(case.asset_glob)
            task = task_store.create(
                TaskCreateRequest(
                    subject="math",
                    asset_path=f"/assets/{source.name}",
                    metadata={
                        "source": f"pi-benchmark-{case.name}",
                        "expected_answer": case.expected_answer,
                    },
                )
            )
            run = runner.enqueue(task.id)
            started = time.monotonic()
            runner.run(task.id, run.id)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            stored_run = run_store.get(run.id)
            stored_task = task_store.get(task.id)
            answer = stored_task.problem.answer.strip() if stored_task.problem else ""
            rows.append(
                {
                    "case": case.name,
                    "task_id": task.id,
                    "run_id": run.id,
                    "expected": case.expected_answer,
                    "answer": answer,
                    "status": stored_run.status.value,
                    "duration_ms": stored_run.duration_ms or elapsed_ms,
                    "stages": stage_durations(stored_run),
                    "input_tokens": stored_run.input_tokens,
                    "output_tokens": stored_run.output_tokens,
                    "cache_tokens": stored_run.cache_tokens,
                    "cost": stored_run.cost,
                    "rpc_log": stored_run.rpc_log_path,
                }
            )
    finally:
        runner.shutdown()
        mcp_runtime.shutdown()

    report = (
        f"Runtime: `{backend.runtime_kind}`"
        f"{f' {backend.runtime_version}' if backend.runtime_version else ''}\n\n"
        + markdown_table(rows)
        + "\n\n"
        + summary_table(rows)
    )
    print(report)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (REPORT_ROOT / f"{stamp}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / f"{stamp}.md").write_text(report + "\n", encoding="utf-8")
    return (
        0
        if all(
            row["status"] == "completed"
            and benchmark_answers_match(str(row["answer"]), str(row["expected"]))
            for row in rows
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
