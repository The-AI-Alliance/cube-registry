"""
Tests for scripts/ownership_check.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import the module under test
from ownership_check import check_ownership, entry_id_from_path


# ─── entry_id_from_path ──────────────────────────────────────────────────────


class TestEntryIdFromPath:
    def test_valid_entry_path(self):
        assert entry_id_from_path("entries/osworld.yaml") == "osworld"

    def test_valid_entry_with_hyphen(self):
        assert entry_id_from_path("entries/webarena-lite.yaml") == "webarena-lite"

    def test_non_entry_yaml(self):
        assert entry_id_from_path("OWNERS.yaml") is None

    def test_nested_path(self):
        # Should not match — entries/ must be the root
        assert entry_id_from_path("stress-results/osworld/v1.json") is None

    def test_non_yaml(self):
        assert entry_id_from_path("entries/osworld.json") is None

    def test_deep_entries(self):
        # entries/subdir/foo.yaml should not match (flat only)
        assert entry_id_from_path("entries/subdir/foo.yaml") is None

    def test_root_yaml(self):
        assert entry_id_from_path("registry-schema.json") is None


# ─── check_ownership ─────────────────────────────────────────────────────────


class TestCheckOwnership:
    def test_new_entry_passes(self):
        """A PR for an entry not in OWNERS.yaml always passes (open submission)."""
        owners = {}  # empty — no existing entries
        result = check_ownership("new-author", ["entries/new-bench.yaml"], owners)
        assert result is True

    def test_author_updating_own_entry_passes(self):
        """Registered owner may update their own entry."""
        owners = {"osworld": ["author-a", "author-b"]}
        result = check_ownership("author-a", ["entries/osworld.yaml"], owners)
        assert result is True

    def test_second_owner_updating_entry_passes(self):
        """Any registered owner may update the entry."""
        owners = {"osworld": ["author-a", "author-b"]}
        result = check_ownership("author-b", ["entries/osworld.yaml"], owners)
        assert result is True

    def test_stranger_blocked(self):
        """An unregistered author trying to modify an existing entry is blocked."""
        owners = {"osworld": ["author-a", "author-b"]}
        result = check_ownership("evil-stranger", ["entries/osworld.yaml"], owners)
        assert result is False

    def test_owners_yaml_modification_blocked(self):
        """Any direct modification of OWNERS.yaml in a PR is blocked."""
        owners = {}
        result = check_ownership("anyone", ["OWNERS.yaml"], owners)
        assert result is False

    def test_stress_results_modification_blocked(self):
        """Modifications to stress-results/ are always blocked."""
        owners = {}
        result = check_ownership("anyone", ["stress-results/osworld/v1.2.0.json"], owners)
        assert result is False

    def test_stress_results_top_level_blocked(self):
        owners = {}
        result = check_ownership("anyone", ["stress-results/"], owners)
        assert result is False

    def test_non_entry_file_passes(self):
        """Changes to other files (README, docs, etc.) are allowed."""
        owners = {}
        result = check_ownership("anyone", ["README.md"], owners)
        assert result is True

    def test_multiple_files_all_pass(self):
        """Multiple changed files — all pass."""
        owners = {"osworld": ["author-a"]}
        result = check_ownership(
            "author-a",
            ["entries/osworld.yaml", "README.md"],
            owners,
        )
        assert result is True

    def test_multiple_files_one_fails(self):
        """Multiple changed files — one fails → overall fail."""
        owners = {
            "osworld": ["author-a"],
            "webarena": ["author-c"],
        }
        # author-a owns osworld but not webarena
        result = check_ownership(
            "author-a",
            ["entries/osworld.yaml", "entries/webarena.yaml"],
            owners,
        )
        assert result is False

    def test_multiple_files_owners_yaml_mixed(self):
        """If OWNERS.yaml is one of the changed files, overall fails even if other files pass."""
        owners = {}
        result = check_ownership(
            "new-author",
            ["entries/new-bench.yaml", "OWNERS.yaml"],
            owners,
        )
        assert result is False

    def test_empty_changed_files(self):
        """No changed files → trivially passes."""
        result = check_ownership("anyone", [], {})
        assert result is True

    def test_at_symbol_stripped_from_pr_author(self):
        """@-prefixed handle should match entry without @ in owners."""
        owners = {"osworld": ["author-a"]}
        # The main() function strips @, but check_ownership receives the bare handle
        result = check_ownership("author-a", ["entries/osworld.yaml"], owners)
        assert result is True

    def test_new_entry_alongside_existing_owned_entry(self):
        """Submitting new entry + updating own entry in same PR."""
        owners = {"osworld": ["author-a"]}
        result = check_ownership(
            "author-a",
            ["entries/osworld.yaml", "entries/brand-new.yaml"],
            owners,
        )
        assert result is True

    def test_stress_results_subdirectory_blocked(self):
        """Modification of any file under stress-results/ is blocked."""
        owners = {}
        result = check_ownership(
            "anyone",
            ["stress-results/osworld/v1.0.0.json"],
            owners,
        )
        assert result is False
