"""Generate tracked OopsNote catalogs from XKW HAR captures."""

from __future__ import annotations

import argparse
from pathlib import Path

from oopsnote.catalog import DATA_DIR
from oopsnote.catalog.xkw import write_catalogs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", nargs="+", type=Path, help="HAR archives containing XKW trees")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    counts = write_catalogs(args.har, args.output_dir)
    print(
        "generated "
        f"{counts['tags']} knowledge tags from {counts['knowledge_subjects']} subjects; "
        f"cleaned {counts['chapter_subjects']} reserve chapter trees"
    )


if __name__ == "__main__":
    main()
