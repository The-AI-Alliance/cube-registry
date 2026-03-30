"""
Tests for registry-schema.json validation.
"""

from __future__ import annotations

import copy

import jsonschema
import pytest


def validate(entry: dict, schema: dict) -> list[str]:
    """Return list of validation error messages."""
    v = jsonschema.Draft7Validator(schema)
    errors = sorted(v.iter_errors(entry), key=lambda e: list(e.path))
    return [e.message for e in errors]


def is_valid(entry: dict, schema: dict) -> bool:
    return len(validate(entry, schema)) == 0


# ─── Valid entries ────────────────────────────────────────────────────────────


class TestValidEntries:
    def test_minimal_entry_passes(self, schema, minimal_entry):
        """Minimal required fields should validate successfully."""
        assert is_valid(minimal_entry, schema)

    def test_full_entry_passes(self, schema, full_entry):
        """Complete entry with all optional fields should validate."""
        assert is_valid(full_entry, schema)

    def test_entry_without_optional_fields(self, schema, minimal_entry):
        """Entry with only required fields is valid."""
        assert is_valid(minimal_entry, schema)

    def test_entry_with_legal_notices(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["notices"] = [
            {
                "type": "third_party_data",
                "description": "Tasks use Reddit data",
                "url": "https://www.redditinc.com/policies/data-api-terms",
            }
        ]
        assert is_valid(e, schema)

    def test_entry_with_all_notice_types(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["notices"] = [
            {"type": "third_party_data", "description": "Reddit data"},
            {"type": "software_registration", "description": "Office license required"},
            {"type": "live_website_clone", "description": "Clones live websites"},
            {"type": "attribution", "description": "Special attribution required"},
        ]
        assert is_valid(e, schema)

    def test_entry_with_multiple_authors(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["authors"] = [
            {"github": "author1", "name": "Author One"},
            {"github": "author2"},
        ]
        assert is_valid(e, schema)

    def test_entry_with_all_tags(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["tags"] = ["web", "coding", "os", "gui", "mobile", "science", "math", "multi-agent"]
        assert is_valid(e, schema)

    def test_entry_with_all_supported_infra(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["supported_infra"] = ["aws", "azure", "gcp", "local"]
        assert is_valid(e, schema)

    def test_entry_with_all_parallelization_modes(self, schema, minimal_entry):
        for mode in ("sequential", "task-parallel", "benchmark-parallel"):
            e = copy.deepcopy(minimal_entry)
            e["parallelization_mode"] = mode
            assert is_valid(e, schema), f"Mode '{mode}' failed validation"

    def test_entry_with_ci_derived_fields(self, schema, full_entry):
        """Full entry including CI-derived fields should pass schema validation."""
        assert is_valid(full_entry, schema)

    def test_archived_status(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["status"] = "archived"
        assert is_valid(e, schema)

    def test_resources_with_vm_config(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["resources"] = [
            {
                "type": "VMResourceConfig",
                "name": "ubuntu-desktop",
                "image_url": "https://example.com/ubuntu.qcow2",
            }
        ]
        assert is_valid(e, schema)

    def test_features_all_false(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["features"] = {"async": False, "streaming": False, "multi_agent": False, "multi_dim_reward": False}
        assert is_valid(e, schema)

    def test_version_with_patch(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["version"] = "1.2.3"
        assert is_valid(e, schema)

    def test_version_without_patch(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["version"] = "2.0"
        assert is_valid(e, schema)


# ─── Missing required fields ──────────────────────────────────────────────────


class TestMissingRequiredFields:
    @pytest.mark.parametrize("field", ["id", "name", "version", "description", "package", "authors"])
    def test_missing_top_level_required_field(self, schema, minimal_entry, field):
        e = copy.deepcopy(minimal_entry)
        del e[field]
        assert not is_valid(e, schema), f"Missing '{field}' should fail"

    def test_missing_legal(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        del e["legal"]
        assert not is_valid(e, schema)

    def test_missing_wrapper_license(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        del e["legal"]["wrapper_license"]
        assert not is_valid(e, schema)

    def test_empty_authors_list(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["authors"] = []
        assert not is_valid(e, schema)

    def test_author_missing_github(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["authors"] = [{"name": "No Handle"}]
        assert not is_valid(e, schema)

    def test_notice_missing_type(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["notices"] = [{"description": "Some notice"}]
        assert not is_valid(e, schema)

    def test_notice_missing_description(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["notices"] = [{"type": "third_party_data"}]
        assert not is_valid(e, schema)


# ─── Wrong types ──────────────────────────────────────────────────────────────


class TestWrongTypes:
    def test_version_must_be_string(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["version"] = 1  # int, not string
        assert not is_valid(e, schema)

    def test_authors_must_be_list(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["authors"] = "not-a-list"
        assert not is_valid(e, schema)

    def test_tags_must_be_list(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["tags"] = "os gui"  # string, not list
        assert not is_valid(e, schema)

    def test_task_count_must_be_integer(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["task_count"] = "369"  # string, not int
        assert not is_valid(e, schema)

    def test_max_concurrent_tasks_must_be_integer(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["max_concurrent_tasks"] = 1.5  # float, not int
        assert not is_valid(e, schema)

    def test_has_debug_task_must_be_bool(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["has_debug_task"] = "yes"
        assert not is_valid(e, schema)

    def test_legal_must_be_object(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"] = "MIT"
        assert not is_valid(e, schema)


# ─── Invalid enum values ──────────────────────────────────────────────────────


class TestInvalidEnums:
    def test_invalid_tag(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["tags"] = ["not-a-valid-tag"]
        assert not is_valid(e, schema)

    def test_invalid_supported_infra(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["supported_infra"] = ["kubernetes"]  # not in enum
        assert not is_valid(e, schema)

    def test_invalid_parallelization_mode(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["parallelization_mode"] = "auto"  # not in enum
        assert not is_valid(e, schema)

    def test_invalid_status(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["status"] = "pending"  # not in enum
        assert not is_valid(e, schema)

    def test_invalid_notice_type(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["notices"] = [{"type": "trademark", "description": "some notice"}]
        assert not is_valid(e, schema)

    def test_supported_infra_empty(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["supported_infra"] = []  # minItems: 1
        assert not is_valid(e, schema)


# ─── Pattern validation ───────────────────────────────────────────────────────


class TestPatternValidation:
    def test_id_with_spaces_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["id"] = "my bench"
        assert not is_valid(e, schema)

    def test_id_uppercase_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["id"] = "MyBench"
        assert not is_valid(e, schema)

    def test_id_leading_hyphen_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["id"] = "-bench"
        assert not is_valid(e, schema)

    def test_valid_id_with_hyphen(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["id"] = "webarena-lite"
        assert is_valid(e, schema)

    def test_description_too_short(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["description"] = "Too short"  # < 10 chars
        assert not is_valid(e, schema)

    def test_version_invalid_format(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["version"] = "v1.0.0"  # leading 'v' not in pattern
        assert not is_valid(e, schema)

    def test_paper_must_be_string(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["paper"] = 12345  # must be a string
        assert not is_valid(e, schema)

    def test_paper_valid_uri(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["paper"] = "https://arxiv.org/abs/2404.07972"
        assert is_valid(e, schema)


# ─── Additional properties ────────────────────────────────────────────────────


class TestAdditionalProperties:
    def test_unknown_top_level_field_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["unknown_field"] = "should not be here"
        assert not is_valid(e, schema)

    def test_unknown_author_field_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["authors"] = [{"github": "author1", "email": "author@example.com"}]
        assert not is_valid(e, schema)

    def test_unknown_legal_field_fails(self, schema, minimal_entry):
        e = copy.deepcopy(minimal_entry)
        e["legal"]["extra_info"] = "some info"
        assert not is_valid(e, schema)
