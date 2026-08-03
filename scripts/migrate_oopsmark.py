"""Report and explicitly apply safe legacy problem migrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from oopsnote.content import prepare_legacy_problem
from oopsnote.core import ContentFormat, Problem, TaskStore


ROOT = Path(__file__).resolve().parents[1]


def _issue_view(issue: Any) -> dict[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "line": issue.line,
        "severity": issue.severity,
    }


def migrate_storage(storage: Path, *, apply: bool = False) -> dict[str, Any]:
    """Return a deterministic report and optionally apply ready migrations."""

    if not storage.is_dir():
        raise FileNotFoundError(f"Migration storage directory does not exist: {storage}")
    store = TaskStore(storage)
    entries: list[dict[str, Any]] = []
    for task in sorted(store.list_all(), key=lambda item: item.id):
        problem = task.problem
        if problem is None or problem.content_format != ContentFormat.LEGACY_MARKDOWN_LATEX:
            continue
        candidate = prepare_legacy_problem(problem.model_dump(mode="python"))
        entry: dict[str, Any] = {
            "task_id": task.id,
            "status": "ready" if candidate.ready else "blocked",
            "issues": [_issue_view(issue) for issue in candidate.issues],
        }
        if apply and candidate.ready:
            try:
                migrated = Problem.model_validate({
                    **problem.model_dump(mode="python"),
                    **candidate.fields,
                    "content_format": ContentFormat.OOPSMARK_V1,
                })
                store.update(task.id, problem=migrated)
                entry["status"] = "migrated"
            except (OSError, RuntimeError, ValueError) as error:
                entry["status"] = "failed"
                entry["error"] = str(error)
        entries.append(entry)
    return {
        "storage": str(storage),
        "mode": "apply" if apply else "report",
        "items": entries,
        "ready": sum(item["status"] == "ready" for item in entries),
        "migrated": sum(item["status"] == "migrated" for item in entries),
        "blocked": sum(item["status"] == "blocked" for item in entries),
        "failed": sum(item["status"] == "failed" for item in entries),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", type=Path, default=ROOT / "storage")
    parser.add_argument("--apply", action="store_true", help="Apply only candidates that pass OopsMark v1 validation")
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path as well as stdout")
    args = parser.parse_args(argv)
    report = migrate_storage(args.storage, apply=args.apply)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_name(f"{args.report.name}.tmp")
        try:
            temporary.write_text(serialized + "\n", encoding="utf-8")
            temporary.replace(args.report)
        finally:
            if temporary.exists():
                temporary.unlink()
    return 1 if report["blocked"] or report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
