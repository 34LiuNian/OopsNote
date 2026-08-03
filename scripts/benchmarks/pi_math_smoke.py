"""Run one image-based Pi smoke task from the canonical benchmark manifest.

The default image is the existing original crop for Example 1.1 in
``storage/assets``. Its reference answer comes from the same manifest used by
the full benchmark, so the two runners have one authoritative case definition.

Usage:
  .venv\\Scripts\\python.exe scripts\\benchmarks\\pi_math_smoke.py
"""

from __future__ import annotations

import argparse
import sys
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

SMOKE_CASE = MATH_BENCHMARK_CASES[0]


def default_image_path() -> Path:
    matches = sorted((ROOT / "storage" / "assets").glob(SMOKE_CASE.asset_glob))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one original crop matching {SMOKE_CASE.asset_glob}, "
            f"found {len(matches)}"
        )
    return matches[0]


def run_task(image_path: Path, expected_option: str, runtime: str) -> int:
    storage = ROOT / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    assets = AssetStore(storage / "assets")
    source = image_path.resolve()
    asset_root = assets.base_dir.resolve()
    asset_path = f"/assets/{source.name}" if source.parent == asset_root else assets.save_file(source)
    task = task_store.create(TaskCreateRequest(
        subject="math",
        asset_path=asset_path,
        metadata={"source": "pi-smoke-example-1.1", "expected_option": expected_option},
    ))
    runner = PiRpcRunner(
        backend=PiRpcBackend(ROOT, runtime=runtime),
        project_root=ROOT,
        task_store=task_store,
        run_store=run_store,
    )
    mcp_runtime = SharedMcpHttpRuntime()
    try:
        runner.set_child_environment(mcp_runtime.start())
        run = runner.enqueue(task.id)
        runner.run(task.id, run.id)
    finally:
        runner.shutdown()
        mcp_runtime.shutdown()

    completed_task = task_store.get(task.id)
    completed_run = run_store.get(run.id)
    print(f"task_id={task.id}")
    print(f"run_id={run.id}")
    print(f"runtime={completed_run.runtime_kind} version={completed_run.runtime_version}")
    print(f"status={completed_task.status.value} run_status={completed_run.status.value}")
    print(f"rpc_log={completed_run.rpc_log_path}")
    if not completed_task.problem:
        return 1
    answer = completed_task.problem.answer.strip()
    print(f"expected_option={expected_option} actual_answer={answer}")
    print(
        "ocr_context="
        f"{completed_task.ocr_context.model_dump(mode='json') if completed_task.ocr_context else None}"
    )
    return 0 if benchmark_answers_match(answer, expected_option) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, help="Use an existing cropped image instead of rendering the Markdown excerpt")
    parser.add_argument("--expected", help="Override the expected answer from the benchmark manifest")
    parser.add_argument("--runtime", choices=("pi", "pi-rust"), default="pi-rust")
    args = parser.parse_args()

    expected_option = args.expected or SMOKE_CASE.expected_answer
    image_path = (args.image or default_image_path()).resolve()
    if not image_path.is_file():
        raise RuntimeError(f"Image not found: {image_path}")
    print(f"image={image_path}")
    print(f"expected_option={expected_option}")
    return run_task(image_path, expected_option, args.runtime)


if __name__ == "__main__":
    sys.exit(main())
