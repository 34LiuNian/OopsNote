"""Run one image-based Pi smoke task from the curated math vault.

The default image is the existing original crop for Example 1.1 in
``storage/assets``. Its reference answer is read from the same Markdown source,
so the smoke test has no second question bank to maintain.

Usage:
  .venv\\Scripts\\python.exe scripts\\benchmarks\\pi_math_smoke.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from oopsnote.ai import PiRpcBackend, PiRpcRunner
from oopsnote.core import AssetStore, RunStore, TaskCreateRequest, TaskStore


ROOT = Path(__file__).resolve().parents[2]
BOOK = ROOT / "vaults" / "新高考数学你真的掌握了吗 函数.md"
DEFAULT_ASSET_GLOB = "*page-6-1.png"


def source_case() -> tuple[str, str]:
    """Read Example 1.1 and its reference option directly from the vault."""
    text = BOOK.read_text(encoding="utf-8")
    question = re.search(r"(【例1\.1】.*?)(?=\n\n【解析1】)", text, flags=re.DOTALL)
    answer = re.search(r"【例1\.1】.*?故选\s*([A-D])", text, flags=re.DOTALL)
    if not question or not answer:
        raise RuntimeError("Could not locate Example 1.1 and its answer in the curated math vault")
    return question.group(1).strip(), answer.group(1)


def default_image_path() -> Path:
    matches = sorted((ROOT / "storage" / "assets").glob(DEFAULT_ASSET_GLOB))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one original crop matching {DEFAULT_ASSET_GLOB}, found {len(matches)}")
    return matches[0]


def run_task(image_path: Path, expected_option: str) -> int:
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
        backend=PiRpcBackend(ROOT),
        project_root=ROOT,
        task_store=task_store,
        run_store=run_store,
    )
    run = runner.enqueue(task.id)
    runner.run(task.id, run.id)

    completed_task = task_store.get(task.id)
    completed_run = run_store.get(run.id)
    print(f"task_id={task.id}")
    print(f"run_id={run.id}")
    print(f"status={completed_task.status.value} run_status={completed_run.status.value}")
    print(f"rpc_log={completed_run.rpc_log_path}")
    if not completed_task.problems:
        return 1
    answer = completed_task.problems[0].answer.strip()
    print(f"expected_option={expected_option} actual_answer={answer}")
    return 0 if answer == expected_option else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, help="Use an existing cropped image instead of rendering the Markdown excerpt")
    args = parser.parse_args()

    question, expected_option = source_case()
    image_path = (args.image or default_image_path()).resolve()
    if not image_path.is_file():
        raise RuntimeError(f"Image not found: {image_path}")
    print(f"image={image_path}")
    print(f"expected_option={expected_option}")
    return run_task(image_path, expected_option)


if __name__ == "__main__":
    sys.exit(main())
