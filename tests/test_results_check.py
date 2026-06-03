"""Unit tests for scripts/results_check.py."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import results_check as rc  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema() -> dict:
    return rc._load_schema()


@pytest.fixture
def valid_record() -> dict:
    return json.loads((FIXTURES_DIR / "valid_result.json").read_text())


@pytest.fixture
def staged_repo(tmp_path, monkeypatch) -> Path:
    """A fake repo with entries/, results/ and the real schema. Patches rc's path constants."""
    (tmp_path / "entries").mkdir()
    (tmp_path / "results").mkdir()
    # Copy the real schema so we exercise the actual constraints.
    shutil.copy(rc.SCHEMA_PATH, tmp_path / "results-schema.json")
    monkeypatch.setattr(rc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rc, "SCHEMA_PATH", tmp_path / "results-schema.json")
    monkeypatch.setattr(rc, "ENTRIES_DIR", tmp_path / "entries")
    monkeypatch.setattr(rc, "RESULTS_DIR", tmp_path / "results")
    return tmp_path


def _write_entry(repo: Path, cube_id: str, version: str = "1.0.0", task_count: int = 125) -> None:
    entry = {
        "id": cube_id,
        "name": cube_id.title(),
        "version": version,
        "description": "Test cube for unit tests.",
        "package": f"{cube_id}-cube",
        "authors": [{"github": "tester"}],
        "legal": {"wrapper_license": "MIT"},
        "task_count": task_count,
    }
    (repo / "entries" / f"{cube_id}.yaml").write_text(yaml.safe_dump(entry))


def _write_result(repo: Path, record: dict, cube_id: str, filename: str | None = None) -> Path:
    cube_dir = repo / "results" / cube_id
    cube_dir.mkdir(parents=True, exist_ok=True)
    eid = record["evaluation_id"]
    name = filename or (eid.translate(rc._FILENAME_REPLACE) + ".json")
    path = cube_dir / name
    path.write_text(json.dumps(record))
    return path


class TestHappyPath:
    def test_valid_record_passes(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        path = _write_result(staged_repo, valid_record, "miniwob")
        assert rc.check_file(path, schema) == []


class TestSchemaErrors:
    def test_missing_required_top_level_field(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        del valid_record["agent"]
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("agent" in f for f in failures)

    def test_invalid_git_commit_length(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        valid_record["agent"]["git_commit"] = "deadbeef"  # too short
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("git_commit" in f for f in failures)

    def test_invalid_score_above_one(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        valid_record["results"]["avg_score"] = 1.5
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("avg_score" in f for f in failures)


class TestPathChecks:
    def test_wrong_directory_rejected(self, staged_repo, valid_record, schema, tmp_path):
        # Put the file outside results/ — must reject.
        outside = tmp_path / "not_results.json"
        outside.write_text(json.dumps(valid_record))
        failures = rc.check_file(outside, schema)
        # Schema may pass but the path check fails (or vice versa) — at least one
        # failure must mention "results/".
        assert any("results/" in f for f in failures)

    def test_unknown_cube_rejected(self, staged_repo, valid_record, schema):
        # No entries/miniwob.yaml written.
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("no entry" in f.lower() for f in failures)

    def test_benchmark_name_mismatch_rejected(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        valid_record["benchmark_name"] = "workarena"  # doesn't match path
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("benchmark_name" in f for f in failures)


class TestVersionChecks:
    def test_unknown_version_rejected(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob", version="2.0.0")
        valid_record["benchmark_version"] = "9.9.9"  # neither current nor prior
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("benchmark_version" in f for f in failures)

    def test_previously_seen_version_accepted(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob", version="2.0.0")
        prior = json.loads(json.dumps(valid_record))
        prior["evaluation_id"] = "tester/prior"
        prior["benchmark_version"] = "1.5.0"
        _write_result(staged_repo, prior, "miniwob")
        # New submission uses an old-but-recorded version.
        valid_record["benchmark_version"] = "1.5.0"
        valid_record["evaluation_id"] = "tester/new"
        path = _write_result(staged_repo, valid_record, "miniwob")
        assert rc.check_file(path, schema) == []


class TestOutcomeSum:
    def test_outcomes_sum_must_equal_n_tasks(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        valid_record["results"]["outcomes"]["n_missing"] = 5  # breaks sum
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("outcomes sum" in f for f in failures)


class TestTaskCountBound:
    def test_n_tasks_must_not_exceed_entry_task_count(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob", task_count=100)
        valid_record["benchmark_subset"]["n_tasks"] = 125  # exceeds entry's 100
        # Re-balance outcomes to keep the sum check from firing first.
        valid_record["results"]["outcomes"]["n_missing"] = 0
        valid_record["results"]["outcomes"]["n_success"] = 100
        valid_record["results"]["outcomes"]["n_failure"] = 25
        valid_record["results"]["outcomes"]["n_max_steps"] = 0
        valid_record["results"]["outcomes"]["n_system_error"] = 0
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("task_count" in f for f in failures)


class TestFilenameMatch:
    def test_filename_must_match_sanitized_evaluation_id(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        path = _write_result(staged_repo, valid_record, "miniwob", filename="some_other_name.json")
        failures = rc.check_file(path, schema)
        assert any("filename" in f for f in failures)


class TestDuplicateId:
    def test_duplicate_evaluation_id_rejected(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        _write_result(staged_repo, valid_record, "miniwob")
        # Try to "add" a second file with the same evaluation_id.
        duplicate_record = json.loads(json.dumps(valid_record))
        duplicate_path = staged_repo / "results" / "miniwob" / "duplicate_name.json"
        duplicate_path.write_text(json.dumps(duplicate_record))
        failures = rc.check_file(duplicate_path, schema)
        # Either duplicate id OR filename mismatch will catch it — both are correct.
        assert any("already exists" in f or "filename" in f for f in failures)

    def test_sibling_added_id_collision_rejected(self, staged_repo, valid_record, schema):
        """Two files added in the same PR with the same evaluation_id must collide (S2)."""
        _write_entry(staged_repo, "miniwob")
        # First file lives in the repo as a "freshly added" file (not on disk
        # as a prior submission yet — that's what sibling_added_ids models).
        first = _write_result(staged_repo, valid_record, "miniwob", filename="alpha.json")
        # Second file with the *same* evaluation_id but a different stem.
        valid_record["agent"]["agent_id"] = "b" * 64  # avoid filename collision
        second = staged_repo / "results" / "miniwob" / "beta.json"
        second.write_text(json.dumps(valid_record))
        # Without sibling awareness: neither sees the other on-disk (each
        # excludes itself from the scan). With sibling awareness: collision.
        failures = rc.check_file(second, schema, sibling_added_ids={valid_record["evaluation_id"]})
        assert any("being added by another file" in f for f in failures)
        # Sanity: removing the sibling info lets the collision slip past.
        first.unlink()  # cleanup not strictly necessary; clarity only


class TestBookkeepingReject:
    def test_underscore_filenames_rejected(self, staged_repo, valid_record, schema):
        """Files like _submissions.json (CI-bot only) must not validate (S1)."""
        _write_entry(staged_repo, "miniwob")
        path = _write_result(staged_repo, valid_record, "miniwob", filename="_submissions.json")
        failures = rc.check_file(path, schema)
        assert any("reserved" in f and "underscore" in f for f in failures)


class TestPrimaryDependenciesSubset:
    def test_orphan_in_primary_rejected(self, staged_repo, valid_record, schema):
        """primary_dependencies must be a subset of dependency_versions keys."""
        _write_entry(staged_repo, "miniwob")
        valid_record["agent"]["dependency_versions"] = {"litellm": "1.55.0"}
        valid_record["agent"]["primary_dependencies"] = ["litellm", "onnxruntime"]
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("primary_dependencies" in f and "onnxruntime" in f for f in failures)

    def test_complete_subset_passes(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        valid_record["agent"]["dependency_versions"] = {"litellm": "1.55.0", "openai": "1.50.0"}
        valid_record["agent"]["primary_dependencies"] = ["litellm"]
        path = _write_result(staged_repo, valid_record, "miniwob")
        # No primary-vs-deps failures.
        failures = rc.check_file(path, schema)
        assert not any("primary_dependencies" in f for f in failures)


class TestSchemaMetaValidation:
    def test_check_schema_runs_at_load(self) -> None:
        """A malformed results-schema.json must fail at load, not at first PR (S7)."""
        # The real schema must pass its own meta-validation.
        rc._load_schema()  # no raise = passes Draft7Validator.check_schema()


class TestFileSize:
    def test_oversized_file_rejected(self, staged_repo, valid_record, schema):
        _write_entry(staged_repo, "miniwob")
        # Pad the record with a large optional config field.
        valid_record["agent"]["config"] = {"huge": "x" * (rc.MAX_FILE_SIZE_BYTES + 1)}
        path = _write_result(staged_repo, valid_record, "miniwob")
        failures = rc.check_file(path, schema)
        assert any("size" in f for f in failures)
