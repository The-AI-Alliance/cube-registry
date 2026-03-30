"""
Tests for site-src/generate.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


# Ensure generate module is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "site-src"))

import generate as gen


# ─── Helpers ─────────────────────────────────────────────────────────────────


def write_entry(path: Path, entry: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(entry, f)


def minimal_entry(entry_id: str, **kwargs) -> dict:
    base = {
        "id": entry_id,
        "name": f"Benchmark {entry_id}",
        "version": "1.0.0",
        "description": "A benchmark for testing the site generator.",
        "package": f"{entry_id}-cube",
        "authors": [{"github": "test-author"}],
        "legal": {"wrapper_license": "MIT"},
        "status": "active",
    }
    base.update(kwargs)
    return base


# ─── enrich_entry ─────────────────────────────────────────────────────────────


class TestEnrichEntry:
    def test_minimal_entry_enriched_without_error(self):
        entry = minimal_entry("test")
        enriched = gen.enrich_entry(entry)
        assert enriched["status"] == "active"
        assert "status_badge" in enriched
        assert enriched["status_badge"]["label"] == "Active"

    def test_active_badge(self):
        entry = minimal_entry("test", status="active")
        enriched = gen.enrich_entry(entry)
        assert "green" in enriched["status_badge"]["bg"]

    def test_degraded_badge(self):
        entry = minimal_entry("test", status="degraded")
        enriched = gen.enrich_entry(entry)
        assert enriched["status_badge"]["label"] == "Degraded"
        assert "yellow" in enriched["status_badge"]["bg"]

    def test_archived_badge(self):
        entry = minimal_entry("test", status="archived")
        enriched = gen.enrich_entry(entry)
        assert enriched["status_badge"]["label"] == "Archived"

    def test_missing_status_defaults_to_active(self):
        entry = minimal_entry("test")
        del entry["status"]
        enriched = gen.enrich_entry(entry)
        assert enriched["status"] == "active"

    def test_description_truncated_at_200_chars(self):
        long_desc = "A" * 250
        entry = minimal_entry("test", description=long_desc)
        enriched = gen.enrich_entry(entry)
        assert len(enriched["description_short"]) <= 203  # 200 + "…"
        assert enriched["description_short"].endswith("…")

    def test_short_description_not_truncated(self):
        entry = minimal_entry("test", description="Short description.")
        enriched = gen.enrich_entry(entry)
        assert enriched["description_short"] == "Short description."
        assert "…" not in enriched["description_short"]

    def test_tag_chips_generated(self):
        entry = minimal_entry("test", tags=["web", "coding"])
        enriched = gen.enrich_entry(entry)
        chips = enriched["tag_chips"]
        assert len(chips) == 2
        labels = [c["label"] for c in chips]
        assert "web" in labels
        assert "coding" in labels

    def test_unknown_tag_gets_default_color(self):
        entry = minimal_entry("test", tags=["some-unknown-tag"])
        enriched = gen.enrich_entry(entry)
        chip = enriched["tag_chips"][0]
        # Should still have a class, not blow up
        assert chip["cls"]

    def test_no_tags_produces_empty_chips(self):
        entry = minimal_entry("test")
        entry.pop("tags", None)
        enriched = gen.enrich_entry(entry)
        assert enriched["tag_chips"] == []

    def test_features_list_only_enabled(self):
        entry = minimal_entry("test")
        entry["features"] = {"async": True, "streaming": False, "multi_agent": True, "multi_dim_reward": False}
        enriched = gen.enrich_entry(entry)
        assert "async" in enriched["features_list"]
        assert "multi_agent" in enriched["features_list"]
        assert "streaming" not in enriched["features_list"]

    def test_pip_install_command(self):
        entry = minimal_entry("test", package="my-benchmark-cube")
        enriched = gen.enrich_entry(entry)
        assert enriched["pip_install"] == "pip install my-benchmark-cube"

    def test_bench_license_verified_flag(self):
        entry = minimal_entry("test")
        entry["legal"]["benchmark_license"] = {"verified_by_original_authors": True}
        enriched = gen.enrich_entry(entry)
        assert enriched["bench_license_verified"] is True

    def test_bench_license_not_verified_by_default(self):
        entry = minimal_entry("test")
        enriched = gen.enrich_entry(entry)
        assert enriched["bench_license_verified"] is False


# ─── generate() ──────────────────────────────────────────────────────────────


class TestGenerate:
    def _setup_entries(self, tmp_path: Path, entries: list[dict]) -> None:
        """Write entries to a temp entries/ directory and patch generate.ENTRIES_DIR and DOCS_DIR."""
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir(parents=True)
        for entry in entries:
            write_entry(entries_dir / f"{entry['id']}.yaml", entry)

    def test_index_page_generated(self, tmp_path):
        entries = [
            minimal_entry("bench-a"),
            minimal_entry("bench-b"),
        ]
        self._setup_entries(tmp_path, entries)
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        index_path = docs_dir / "index.html"
        assert index_path.exists()
        content = index_path.read_text()
        assert "bench-a" in content
        assert "bench-b" in content

    def test_per_benchmark_pages_generated(self, tmp_path):
        entries = [minimal_entry("alpha"), minimal_entry("beta")]
        self._setup_entries(tmp_path, entries)
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        assert (docs_dir / "alpha" / "index.html").exists()
        assert (docs_dir / "beta" / "index.html").exists()

    def test_benchmark_page_contains_name(self, tmp_path):
        entry = minimal_entry("my-bench", name="Amazing Benchmark")
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        content = (docs_dir / "my-bench" / "index.html").read_text()
        assert "Amazing Benchmark" in content

    def test_missing_optional_fields_handled_gracefully(self, tmp_path):
        """Entry with only required fields should generate pages without crashing."""
        entry = {
            "id": "bare-minimum",
            "name": "Bare Minimum",
            "version": "0.1.0",
            "description": "Has only required fields, no optional ones.",
            "package": "bare-minimum-cube",
            "authors": [{"github": "nobody"}],
            "legal": {"wrapper_license": "MIT"},
        }
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)  # should not raise
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        assert (docs_dir / "bare-minimum" / "index.html").exists()

    def test_degraded_entry_shows_degraded_badge(self, tmp_path):
        entry = minimal_entry("degraded-bench", status="degraded")
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        index_content = (docs_dir / "index.html").read_text()
        assert "Degraded" in index_content

        bench_content = (docs_dir / "degraded-bench" / "index.html").read_text()
        assert "Degraded" in bench_content

    def test_empty_entries_dir_generates_empty_index(self, tmp_path):
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = entries_dir
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        # Index should still be generated
        assert (docs_dir / "index.html").exists()

    def test_dry_run_does_not_write_files(self, tmp_path):
        entry = minimal_entry("dry-run-bench")
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=True)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        # No files should be written in dry-run mode
        assert not (docs_dir / "index.html").exists()

    def test_index_contains_filter_bar(self, tmp_path):
        entry = minimal_entry("bench", tags=["web", "coding"])
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        content = (docs_dir / "index.html").read_text()
        assert "filter" in content.lower() or "search" in content.lower()

    def test_benchmark_page_has_pip_install_copy_button(self, tmp_path):
        entry = minimal_entry("copy-bench", package="copy-bench-cube")
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        content = (docs_dir / "copy-bench" / "index.html").read_text()
        assert "pip install copy-bench-cube" in content
        assert "Copy" in content or "copy" in content

    def test_benchmark_page_legal_section(self, tmp_path):
        entry = minimal_entry("legal-bench")
        entry["legal"]["benchmark_license"] = {
            "reported": "CC-BY-NC-4.0",
            "source_url": "https://example.com/LICENSE",
            "verified_by_original_authors": False,
        }
        entry["legal"]["notices"] = [
            {"type": "third_party_data", "description": "Uses Reddit data"}
        ]
        self._setup_entries(tmp_path, [entry])
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        content = (docs_dir / "legal-bench" / "index.html").read_text()
        assert "CC-BY-NC-4.0" in content
        assert "Self-reported" in content
        assert "Reddit data" in content

    def test_all_entries_appear_in_index(self, tmp_path):
        entries = [minimal_entry(f"bench-{i}") for i in range(5)]
        self._setup_entries(tmp_path, entries)
        docs_dir = tmp_path / "docs"

        import generate as mod
        orig_entries = mod.ENTRIES_DIR
        orig_docs = mod.DOCS_DIR
        mod.ENTRIES_DIR = tmp_path / "entries"
        mod.DOCS_DIR = docs_dir

        try:
            gen.generate(dry_run=False)
        finally:
            mod.ENTRIES_DIR = orig_entries
            mod.DOCS_DIR = orig_docs

        content = (docs_dir / "index.html").read_text()
        for i in range(5):
            assert f"bench-{i}" in content
