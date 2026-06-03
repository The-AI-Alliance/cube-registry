#!/usr/bin/env python3
"""
results_check.py — validate community-submitted result JSON files.

Validates each added file under ``results/<cube-id>/*.json`` against
``results-schema.json`` plus a set of cross-references to the registry
(``entries/<cube-id>.yaml``) and consistency checks (outcomes sum, filename
matches evaluation_id, file size, dedup within the cube's directory).

The PR-level path-isolation gate (auto-merge eligibility) is handled by the
calling workflow — this script validates one batch of added files and prints
a markdown summary suitable for a PR comment.

Exit codes:
  0 — every added file passed every check
  1 — at least one file failed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
from ruamel.yaml import YAML

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
SCHEMA_PATH = REPO_ROOT / "results-schema.json"
ENTRIES_DIR = REPO_ROOT / "entries"
RESULTS_DIR = REPO_ROOT / "results"

MAX_FILE_SIZE_BYTES = 50 * 1024  # 50 KB

# Slash → __ when sanitizing evaluation_id into a filename stem.
_FILENAME_REPLACE = str.maketrans({"/": "__"})

# Mirrors the schema: benchmark_name pattern.
_CUBE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class CheckError(Exception):
    """Raised per check. Message is shown verbatim in the PR comment."""


def _load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    # Cheap meta-validation: catches typos in results-schema.json at CI start
    # instead of letting every PR runner re-discover the breakage (S7).
    jsonschema.Draft7Validator.check_schema(schema)
    return schema


def _load_yaml(path: Path) -> dict:
    return YAML().load(path.read_text())


def _file_to_cube_id(file_path: Path) -> str:
    """``results/<cube-id>/<file>.json`` → ``<cube-id>``. Raises on shape mismatch."""
    try:
        relative = file_path.resolve().relative_to(RESULTS_DIR.resolve())
    except ValueError as e:
        raise CheckError(f"file is not under results/: {file_path}") from e
    if len(relative.parts) != 2 or not relative.name.endswith(".json"):
        raise CheckError(f"expected results/<cube-id>/<file>.json, got results/{relative}")
    # Bot-only bookkeeping files (e.g. _submissions.json) MUST NOT come in via
    # community PRs. The workflow filters them at the changed-files step; this
    # is the script-side defense in depth (S1).
    if relative.name.startswith("_"):
        raise CheckError(
            f"filename '{relative.name}' is reserved for CI-bot bookkeeping; "
            "community submissions cannot use a leading underscore"
        )
    cube_id = relative.parts[0]
    if not _CUBE_ID_RE.match(cube_id):
        raise CheckError(f"cube-id segment '{cube_id}' is not a valid slug")
    return cube_id


def _entry_for(cube_id: str) -> dict:
    """Read the registry entry for *cube_id*; raise if missing."""
    entry_path = ENTRIES_DIR / f"{cube_id}.yaml"
    if not entry_path.exists():
        raise CheckError(
            f"cube-id '{cube_id}' has no entry at entries/{cube_id}.yaml — "
            "register the benchmark first"
        )
    entry = _load_yaml(entry_path)
    if not isinstance(entry, dict):
        raise CheckError(f"entries/{cube_id}.yaml could not be parsed")
    return entry


def _known_versions_for(cube_id: str, current_version: str, excluding: Path) -> set[str]:
    """Union of the entry's current version + any version already in results/<cube_id>/.

    *excluding* is the file currently being validated; the function must not count
    it as prior evidence of its own version.
    """
    versions = {current_version}
    cube_results_dir = RESULTS_DIR / cube_id
    if not cube_results_dir.exists():
        return versions
    excluding_resolved = excluding.resolve()
    for prior in cube_results_dir.glob("*.json"):
        if prior.name.startswith("_") or prior.resolve() == excluding_resolved:
            continue
        try:
            data = json.loads(prior.read_text())
        except json.JSONDecodeError:
            continue
        prior_version = data.get("benchmark_version")
        if isinstance(prior_version, str):
            versions.add(prior_version)
    return versions


def _existing_evaluation_ids(cube_id: str, excluding: Path) -> set[str]:
    """All evaluation_id values currently in results/<cube_id>/, excluding *excluding*."""
    cube_results_dir = RESULTS_DIR / cube_id
    if not cube_results_dir.exists():
        return set()
    ids: set[str] = set()
    excluding_resolved = excluding.resolve()
    for prior in cube_results_dir.glob("*.json"):
        if prior.name.startswith("_") or prior.resolve() == excluding_resolved:
            continue
        try:
            data = json.loads(prior.read_text())
        except json.JSONDecodeError:
            continue
        eid = data.get("evaluation_id")
        if isinstance(eid, str):
            ids.add(eid)
    return ids


def _validate_against_schema(record: dict, schema: dict) -> list[str]:
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    return [f"schema: {'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def check_file(
    file_path: Path,
    schema: dict,
    *,
    sibling_added_ids: set[str] | None = None,
) -> list[str]:
    """Run every check on one added file. Returns the list of failure messages.

    *sibling_added_ids* (S2) is the set of ``evaluation_id`` values *also*
    being added in the same PR batch (excluding *file_path* itself). The
    uniqueness check unions this with the on-disk set so two files in the
    same PR can't both pass with identical IDs — the on-disk view is the
    same for each when neither is merged yet.
    """
    failures: list[str] = []

    if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
        return [
            f"file size {file_path.stat().st_size} bytes exceeds the "
            f"{MAX_FILE_SIZE_BYTES}-byte cap — results must be aggregates only, "
            "not per-task data"
        ]

    try:
        cube_id = _file_to_cube_id(file_path)
    except CheckError as e:
        return [str(e)]

    try:
        record = json.loads(file_path.read_text())
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]

    failures.extend(_validate_against_schema(record, schema))
    if failures:
        # Skip semantic checks when the schema itself didn't validate — fields may
        # be missing or the wrong type, so semantic checks would crash unhelpfully.
        return failures

    # ── Cross-reference: the cube must be registered ────────────────────────
    try:
        entry = _entry_for(cube_id)
    except CheckError as e:
        return [str(e)]

    # ── benchmark_name matches the path's cube-id ───────────────────────────
    if record["benchmark_name"] != cube_id:
        failures.append(
            f"benchmark_name '{record['benchmark_name']}' does not match the "
            f"path's cube-id '{cube_id}'"
        )

    # ── benchmark_version is known (current entry, or previously seen) ──────
    entry_version = entry.get("version", "")
    if not isinstance(entry_version, str) or not entry_version:
        failures.append(f"entries/{cube_id}.yaml has no usable version field")
    else:
        known = _known_versions_for(cube_id, entry_version, excluding=file_path)
        if record["benchmark_version"] not in known:
            failures.append(
                f"benchmark_version '{record['benchmark_version']}' is not known — "
                f"the registry has '{entry_version}' and prior results have "
                f"{sorted(known - {entry_version}) or 'none'}"
            )

    # ── n_tasks ≤ task_count from the entry ─────────────────────────────────
    entry_task_count = entry.get("task_count")
    if isinstance(entry_task_count, int) and entry_task_count > 0:
        if record["benchmark_subset"]["n_tasks"] > entry_task_count:
            failures.append(
                f"benchmark_subset.n_tasks ({record['benchmark_subset']['n_tasks']}) "
                f"exceeds entries/{cube_id}.yaml task_count ({entry_task_count})"
            )

    # ── outcomes sum equals n_tasks (mutually exclusive + exhaustive) ───────
    outcomes = record["results"]["outcomes"]
    outcomes_sum = sum(
        outcomes[k]
        for k in ("n_success", "n_failure", "n_max_steps", "n_system_error", "n_missing")
    )
    n_tasks = record["benchmark_subset"]["n_tasks"]
    if outcomes_sum != n_tasks:
        failures.append(
            f"outcomes sum ({outcomes_sum}) does not equal "
            f"benchmark_subset.n_tasks ({n_tasks}) — "
            f"the five counts must be mutually exclusive and exhaustive"
        )

    # ── primary_dependencies ⊆ dependency_versions ──────────────────────────
    # The schema describes primary_dependencies as "Subset of
    # dependency_versions" but doesn't structurally enforce it. Without this
    # check, a submitter listing ["onnxruntime"] while dependency_versions
    # only knows {"torch": ...} would silently produce a bogus primary tier
    # in the UI (every column would render "— missing" for the orphaned name).
    primary = record.get("agent", {}).get("primary_dependencies") or []
    dep_versions = record.get("agent", {}).get("dependency_versions") or {}
    orphans = [p for p in primary if p not in dep_versions]
    if orphans:
        failures.append(
            f"agent.primary_dependencies contains {len(orphans)} entries not "
            f"present in agent.dependency_versions: {sorted(orphans)[:5]}"
            + ("…" if len(orphans) > 5 else "")
        )

    # ── filename matches the sanitized evaluation_id ────────────────────────
    expected_stem = record["evaluation_id"].translate(_FILENAME_REPLACE)
    if file_path.stem != expected_stem:
        failures.append(
            f"filename stem '{file_path.stem}' does not match sanitized "
            f"evaluation_id '{expected_stem}' (slashes → __)"
        )

    # ── evaluation_id is globally unique within results/<cube>/ ─────────────
    # Two independent checks (S2) — both fire even when they overlap, because
    # they cover different invocation contexts:
    #   - on-disk: the validator runs on a CI checkout that already has every
    #     added file, so a dup between batch siblings IS visible here.
    #   - sibling-batch: defense in depth for local invocations where the
    #     argv list is the only source of truth (the batch is in flight, not
    #     all files necessarily on disk yet).
    if record["evaluation_id"] in _existing_evaluation_ids(cube_id, file_path):
        failures.append(
            f"evaluation_id '{record['evaluation_id']}' already exists in "
            f"results/{cube_id}/ — use 'supersedes' with a new id to correct a prior submission"
        )
    if record["evaluation_id"] in (sibling_added_ids or set()):
        failures.append(
            f"evaluation_id '{record['evaluation_id']}' is being added by another file "
            "in this same PR — each submission needs a unique id"
        )

    return failures


def _format_summary(per_file: dict[Path, list[str]]) -> str:
    """Markdown summary suitable for a PR comment."""
    lines = ["## Results check"]
    all_passed = all(not failures for failures in per_file.values())
    if all_passed:
        lines.append("")
        lines.append(f"✅ All {len(per_file)} file(s) passed validation.")
        return "\n".join(lines)

    lines.append("")
    lines.append("❌ The following file(s) did not pass validation:")
    lines.append("")
    for fp, failures in per_file.items():
        if failures:
            lines.append(f"### `{fp}`")
            for msg in failures:
                lines.append(f"- {msg}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--added",
        nargs="*",
        default=[],
        help="Paths of files added in this PR. Expected to all be under results/.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="If set, write the markdown summary to this path (for the workflow to comment).",
    )
    args = parser.parse_args()

    if not args.added:
        print("No added files to check.")
        return 0

    schema = _load_schema()
    # Pre-collect every evaluation_id this PR is attempting to add so any
    # check_file invocation can see the rest of its own batch (S2).
    added_paths = [Path(p) for p in args.added]
    batch_ids: dict[Path, str] = {}
    for path in added_paths:
        try:
            batch_ids[path] = json.loads(path.read_text()).get("evaluation_id")
        except Exception:
            batch_ids[path] = None
    per_file: dict[Path, list[str]] = {}
    for path in added_paths:
        siblings = {eid for p, eid in batch_ids.items() if p != path and isinstance(eid, str)}
        per_file[path] = check_file(path, schema, sibling_added_ids=siblings)

    summary = _format_summary(per_file)
    print(summary)
    if args.summary_out is not None:
        args.summary_out.write_text(summary)

    return 0 if all(not failures for failures in per_file.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
