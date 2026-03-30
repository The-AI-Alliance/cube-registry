"""
Tests for scripts/update_owners.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ruamel.yaml import YAML

from update_owners import update_owners


def read_owners(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_entry(path: Path, entry: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(entry, f)


# ─── Core behaviour ───────────────────────────────────────────────────────────


class TestUpdateOwners:
    def test_new_entry_added(self, tmp_path, minimal_entry):
        """New entry not yet in OWNERS.yaml should be added."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("")  # empty

        entry_path = tmp_path / "entries" / "my-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, minimal_entry)

        # Patch OWNERS_PATH to point to tmp
        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path
        try:
            modified = update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

        assert modified is True
        owners = read_owners(owners_path)
        assert "my-bench" in owners
        assert "author1" in owners["my-bench"]

    def test_existing_entry_updated_with_new_author(self, tmp_path, minimal_entry):
        """Existing entry with new author added via PR should get the new author."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("my-bench:\n  - original-author\n")

        # Entry now has a second author
        entry = {**minimal_entry, "authors": [
            {"github": "original-author"},
            {"github": "new-author"},
        ]}
        entry_path = tmp_path / "entries" / "my-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, entry)

        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path
        try:
            modified = update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

        assert modified is True
        owners = read_owners(owners_path)
        assert "original-author" in owners["my-bench"]
        assert "new-author" in owners["my-bench"]

    def test_idempotent_no_change(self, tmp_path, minimal_entry):
        """Running twice with the same authors produces the same result."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("my-bench:\n  - author1\n")

        entry_path = tmp_path / "entries" / "my-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, minimal_entry)

        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path

        try:
            modified1 = update_owners(entry_path)
            owners_after_first = read_owners(owners_path)

            modified2 = update_owners(entry_path)
            owners_after_second = read_owners(owners_path)
        finally:
            mod.OWNERS_PATH = original

        assert modified1 is False  # already up to date
        assert modified2 is False
        assert owners_after_first == owners_after_second
        assert owners_after_first["my-bench"] == ["author1"]

    def test_other_entries_preserved(self, tmp_path, minimal_entry):
        """Updating one entry does not affect other entries in OWNERS.yaml."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text(
            "existing-bench:\n  - other-author\n"
            "another-bench:\n  - third-author\n"
        )

        entry_path = tmp_path / "entries" / "my-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, minimal_entry)

        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path
        try:
            update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

        owners = read_owners(owners_path)
        assert "existing-bench" in owners
        assert "other-author" in owners["existing-bench"]
        assert "another-bench" in owners
        assert "my-bench" in owners

    def test_multiple_authors(self, tmp_path):
        """Entry with multiple authors should add all of them."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("")

        entry = {
            "id": "multi-author-bench",
            "name": "Multi-Author Benchmark",
            "version": "1.0.0",
            "description": "A benchmark with multiple authors.",
            "package": "multi-bench",
            "authors": [
                {"github": "alice"},
                {"github": "bob", "name": "Bob"},
                {"github": "charlie"},
            ],
            "legal": {"wrapper_license": "Apache-2.0"},
        }

        entry_path = tmp_path / "entries" / "multi-author-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, entry)

        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path
        try:
            update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

        owners = read_owners(owners_path)
        assert set(owners["multi-author-bench"]) == {"alice", "bob", "charlie"}

    def test_no_duplicate_handles(self, tmp_path, minimal_entry):
        """Running update_owners should not produce duplicate handles."""
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("my-bench:\n  - author1\n  - author1\n")  # already duplicate

        entry_path = tmp_path / "entries" / "my-bench.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, minimal_entry)

        import update_owners as mod
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path
        try:
            update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

        owners = read_owners(owners_path)
        # No duplicates after update
        assert len(owners["my-bench"]) == len(set(owners["my-bench"]))

    def test_missing_entry_id_raises(self, tmp_path):
        """Entry without 'id' field should raise ValueError."""
        entry = {
            "name": "No ID",
            "version": "1.0.0",
            "description": "Missing id field.",
            "package": "no-id",
            "authors": [{"github": "author1"}],
            "legal": {"wrapper_license": "MIT"},
        }
        entry_path = tmp_path / "entries" / "no-id.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, entry)

        import update_owners as mod
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("")
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path

        try:
            with pytest.raises(ValueError, match="no 'id' field"):
                update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original

    def test_no_github_handles_raises(self, tmp_path):
        """Entry with authors but no github handles should raise ValueError."""
        entry = {
            "id": "no-github",
            "name": "No GitHub",
            "version": "1.0.0",
            "description": "Authors without github handles.",
            "package": "no-github",
            "authors": [{"name": "Author Without Handle"}],
            "legal": {"wrapper_license": "MIT"},
        }
        entry_path = tmp_path / "entries" / "no-github.yaml"
        entry_path.parent.mkdir(parents=True)
        write_entry(entry_path, entry)

        import update_owners as mod
        owners_path = tmp_path / "OWNERS.yaml"
        owners_path.write_text("")
        original = mod.OWNERS_PATH
        mod.OWNERS_PATH = owners_path

        try:
            with pytest.raises(ValueError, match="no authors with github handles"):
                update_owners(entry_path)
        finally:
            mod.OWNERS_PATH = original
