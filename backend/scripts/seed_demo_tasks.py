from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo tasks into backend/storage/tasks")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing tasks only when they look like demo/render-test tasks.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    seed_dir = repo_root / "backend" / "dev_seed" / "tasks"
    out_dir = repo_root / "backend" / "storage" / "tasks"

    if not seed_dir.exists():
        print(f"seed dir not found: {seed_dir}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for path in sorted(seed_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        task_id = str(data.get("id") or "").strip()
        if not task_id:
            raise ValueError(f"Seed task missing id: {path}")

        dest = out_dir / f"{task_id}.json"
        if dest.exists() and not args.overwrite:
            continue

        if dest.exists() and args.overwrite:
            try:
                existing = json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                existing = None

            existing_payload = (existing or {}).get("payload") or {}
            existing_source = str(existing_payload.get("source") or "").strip()

            # Safety: only overwrite tasks that appear to be demo/render-test tasks.
            if existing_source != "渲染测试":
                continue

        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count += 1

    print(f"Seeded {count} task(s) into {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
