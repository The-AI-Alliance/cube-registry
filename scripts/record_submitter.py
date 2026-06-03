#!/usr/bin/env python3
"""
record_submitter.py — append PR-author + merge-timestamp entries to per-cube
``results/<cube-id>/_submissions.json`` bookkeeping files.

Called by ``.github/workflows/record-submitter.yml`` on push to main when new
``results/<cube-id>/*.json`` files land. The CI bot owns this file via a
path-restricted bypass rule — humans cannot push to ``_submissions.json``.

File format (per cube):
    {
      "<evaluation_id>": {"submitted_by": "<github-handle>", "merged_at": "<iso8601>"},
      ...
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
RESULTS_DIR = REPO_ROOT / "results"

SUBMISSIONS_FILENAME = "_submissions.json"


def _load_submissions(cube_dir: Path) -> dict[str, dict[str, str]]:
    path = cube_dir / SUBMISSIONS_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_submissions(cube_dir: Path, submissions: dict[str, dict[str, str]]) -> None:
    path = cube_dir / SUBMISSIONS_FILENAME
    # Sort by evaluation_id for stable diffs.
    ordered = dict(sorted(submissions.items()))
    path.write_text(json.dumps(ordered, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", required=True, help="GitHub handle of the PR author.")
    parser.add_argument("--merge-timestamp", required=True, help="ISO-8601 merge timestamp.")
    parser.add_argument("--files", nargs="+", default=[], help="Added result JSON files.")
    args = parser.parse_args()

    by_cube: dict[Path, list[Path]] = defaultdict(list)
    for f in args.files:
        path = Path(f)
        if not path.exists():
            continue  # file may have been moved or deleted since the push
        # Expect results/<cube>/<file>.json
        cube_dir = path.parent
        if cube_dir.parent != RESULTS_DIR:
            continue
        if path.name.startswith("_"):
            continue
        by_cube[cube_dir].append(path)

    for cube_dir, paths in by_cube.items():
        submissions = _load_submissions(cube_dir)
        for path in paths:
            try:
                record = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            eid = record.get("evaluation_id")
            if not isinstance(eid, str):
                continue
            submissions[eid] = {
                "submitted_by": args.author,
                "merged_at": args.merge_timestamp,
            }
        _write_submissions(cube_dir, submissions)

    return 0


if __name__ == "__main__":
    sys.exit(main())
