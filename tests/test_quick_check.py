"""Unit tests for scripts/quick_check.py — pure functions that don't need pip or Docker."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import quick_check as qc  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────


def minimal_entry(**kwargs) -> dict:
    base = {
        "id": "counter-cube",
        "name": "Counter Cube",
        "version": "0.1.0",
        "description": "A simple test benchmark.",
        "package": "counter-cube",
        "authors": [{"github": "alice"}],
        "legal": {"wrapper_license": "MIT"},
        "tags": ["math"],
    }
    base.update(kwargs)
    return base


def load_schema_fixture() -> dict:
    schema_path = Path(__file__).parent.parent / "registry-schema.json"
    with open(schema_path) as f:
        return json.load(f)


# ── validate_schema ───────────────────────────────────────────────────────────


class TestValidateSchema:
    def setup_method(self):
        self.schema = load_schema_fixture()

    def test_valid_entry_returns_no_errors(self):
        errors = qc.validate_schema(minimal_entry(), self.schema)
        assert errors == []

    def test_missing_required_field_returns_error(self):
        entry = minimal_entry()
        del entry["name"]
        errors = qc.validate_schema(entry, self.schema)
        assert any("name" in e for e in errors)

    def test_invalid_package_name_returns_error(self):
        errors = qc.validate_schema(minimal_entry(package="UPPERCASE-Invalid"), self.schema)
        assert len(errors) > 0

    def test_invalid_dev_install_url_domain_rejected(self):
        errors = qc.validate_schema(
            minimal_entry(dev_install_url="git+https://bitbucket.org/org/repo"),
            self.schema,
        )
        assert len(errors) > 0

    def test_valid_github_dev_install_url_accepted(self):
        errors = qc.validate_schema(
            minimal_entry(dev_install_url="git+https://github.com/org/repo"),
            self.schema,
        )
        assert errors == []

    def test_empty_authors_list_returns_error(self):
        errors = qc.validate_schema(minimal_entry(authors=[]), self.schema)
        assert len(errors) > 0

    def test_invalid_tag_returns_error(self):
        errors = qc.validate_schema(minimal_entry(tags=["notavalidtag"]), self.schema)
        assert len(errors) > 0


# ── _serialize_resource ───────────────────────────────────────────────────────


class TestSerializeResource:
    def test_pydantic_model_serialized(self):
        class FakeResource:
            def model_dump(self):
                return {"image_url": "docker.io/foo"}

        result = qc._serialize_resource(FakeResource())
        assert result["image_url"] == "docker.io/foo"
        assert result["type"] == "FakeResource"

    def test_legacy_dict_method_serialized(self):
        class LegacyResource:
            def dict(self):
                return {"image_url": "docker.io/bar"}

        result = qc._serialize_resource(LegacyResource())
        assert result["image_url"] == "docker.io/bar"
        assert result["type"] == "LegacyResource"

    def test_plain_object_via_vars(self):
        class PlainResource:
            def __init__(self):
                self.image_url = "docker.io/baz"

        result = qc._serialize_resource(PlainResource())
        assert result["image_url"] == "docker.io/baz"
        assert result["type"] == "PlainResource"


# ── check_verified_by_original_authors ───────────────────────────────────────


class TestCheckVerifiedByOriginalAuthors:
    def test_pr_author_is_known_returns_true(self):
        entry = minimal_entry(id="my-bench", authors=[{"github": "alice"}])
        known = {"my-bench": ["alice", "bob"]}
        assert qc.check_verified_by_original_authors(entry, "alice", known) is True

    def test_entry_author_is_known_returns_true(self):
        entry = minimal_entry(id="my-bench", authors=[{"github": "alice"}])
        known = {"my-bench": ["alice"]}
        assert qc.check_verified_by_original_authors(entry, "charlie", known) is True

    def test_unknown_pr_author_and_entry_authors_returns_false(self):
        entry = minimal_entry(id="my-bench", authors=[{"github": "stranger"}])
        known = {"my-bench": ["alice"]}
        assert qc.check_verified_by_original_authors(entry, "stranger", known) is False

    def test_benchmark_not_in_known_authors_returns_false(self):
        entry = minimal_entry(id="my-bench", authors=[{"github": "alice"}])
        known = {}
        assert qc.check_verified_by_original_authors(entry, "alice", known) is False

    def test_none_pr_author_still_checks_entry_authors(self):
        entry = minimal_entry(id="my-bench", authors=[{"github": "alice"}])
        known = {"my-bench": ["alice"]}
        assert qc.check_verified_by_original_authors(entry, None, known) is True


# ── write_derived_fields ──────────────────────────────────────────────────────


class TestWriteDerivedFields:
    def _write_entry(self, path: Path, entry: dict) -> None:
        from ruamel.yaml import YAML
        yaml = YAML()
        with open(path, "w") as f:
            yaml.dump(entry, f)

    def test_status_set_to_active(self, tmp_path):
        entry = minimal_entry()
        entry_path = tmp_path / "counter-cube.yaml"
        self._write_entry(entry_path, entry)
        derived = {"task_count": 5, "has_debug_task": True, "has_debug_agent": False,
                   "resources": [], "features": {}, "action_space": []}
        qc.write_derived_fields(entry_path, entry, derived, pr_author=None)
        from ruamel.yaml import YAML
        result = YAML().load(entry_path.read_text())
        assert result["status"] == "active"
        assert result["task_count"] == 5

    def test_archived_status_not_overwritten(self, tmp_path):
        entry = minimal_entry(status="archived")
        entry_path = tmp_path / "counter-cube.yaml"
        self._write_entry(entry_path, entry)
        derived = {"task_count": 1, "has_debug_task": True, "has_debug_agent": False,
                   "resources": [], "features": {}, "action_space": []}
        qc.write_derived_fields(entry_path, entry, derived, pr_author=None)
        from ruamel.yaml import YAML
        result = YAML().load(entry_path.read_text())
        assert result["status"] == "archived"

    def test_integrity_check_catches_round_trip_mutation(self, tmp_path):
        entry = minimal_entry()
        entry_path = tmp_path / "counter-cube.yaml"
        self._write_entry(entry_path, entry)
        # Tamper: pass entry with different id than what's on disk
        tampered_entry = dict(entry)
        tampered_entry["id"] = "different-id"
        derived = {"task_count": 1, "has_debug_task": True, "has_debug_agent": False,
                   "resources": [], "features": {}, "action_space": []}
        with pytest.raises(RuntimeError, match="Integrity check failed"):
            qc.write_derived_fields(entry_path, tampered_entry, derived, pr_author=None)


# ── ownership_check handle validation ────────────────────────────────────────


class TestOwnershipCheckHandleValidation:
    """Test the PR author handle validation added as a security defence."""

    def _run(self, *args):
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import ownership_check as oc
        with patch.object(sys, "argv", ["ownership_check.py"] + list(args)):
            with patch("ownership_check.read_owners_from_main", return_value={}):
                try:
                    oc.main()
                    return 0
                except SystemExit as e:
                    return e.code

    def test_valid_handle_passes(self):
        code = self._run("--pr-author", "alice", "--changed-files", "entries/a.yaml")
        assert code == 0

    def test_handle_with_special_chars_rejected(self):
        code = self._run("--pr-author", "alice; rm -rf /", "--changed-files", "entries/a.yaml")
        assert code == 1

    def test_handle_with_at_prefix_stripped_and_valid(self):
        code = self._run("--pr-author", "@alice", "--changed-files", "entries/a.yaml")
        assert code == 0

    def test_path_traversal_in_changed_files_rejected(self):
        code = self._run("--pr-author", "alice", "--changed-files", "../etc/passwd")
        assert code == 1
