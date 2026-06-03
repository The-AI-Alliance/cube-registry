"""Unit tests for scripts/entry_review.py.

The actual Anthropic API call is mocked — we test context assembly, verdict
parsing, comment rendering, and main()'s file I/O.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import entry_review as er  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────


def write_entry(tmp_path: Path, entry: dict) -> Path:
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir(exist_ok=True)
    p = entries_dir / f"{entry['id']}.yaml"
    p.write_text(yaml.safe_dump(entry, sort_keys=False))
    return p


def minimal_entry(**kwargs) -> dict:
    base = {
        "id": "fakebench",
        "name": "Fakebench",
        "version": "0.1.0",
        "description": "A fake benchmark for testing.",
        "package": "fakebench-cube",
        "dev_install_url": "git+https://github.com/example/fakebench-cube",
        "authors": [{"github": "alice", "name": "Alice"}],
        "legal": {"wrapper_license": "MIT"},
        "tags": ["math"],
    }
    base.update(kwargs)
    return base


def good_verdict() -> dict:
    return {
        "verdict": "PASS",
        "checks": {k: "pass" for k in er.CHECK_KEYS},
        "notes": "Looks fine.",
    }


def concern_verdict() -> dict:
    v = good_verdict()
    v["verdict"] = "CONCERN"
    v["checks"]["no_brand_impersonation"] = "fail"
    v["notes"] = "Name resembles a famous benchmark with no clear upstream link."
    return v


# ── context assembly ────────────────────────────────────────────────────────


class TestBuildContext:
    def test_includes_entry_yaml_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        entry_path = write_entry(tmp_path, minimal_entry())
        ctx, entry = er.build_context(entry_path)
        assert "## ENTRY UNDER REVIEW" in ctx
        assert "id: fakebench" in ctx
        assert entry["id"] == "fakebench"

    def test_includes_pypi_info_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(
            er, "fetch_pypi",
            lambda pkg: {
                "info": {
                    "summary": "a fake test benchmark",
                    "license": "MIT",
                    "description": "Long description here.",
                }
            },
        )
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        entry_path = write_entry(tmp_path, minimal_entry())
        ctx, _ = er.build_context(entry_path)
        assert "a fake test benchmark" in ctx
        assert "License field (from PyPI): MIT" in ctx
        assert "Long description here." in ctx

    def test_handles_missing_pypi(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        entry_path = write_entry(tmp_path, minimal_entry())
        ctx, _ = er.build_context(entry_path)
        assert "package may be unpublished" in ctx

    def test_handles_missing_readme(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        entry_path = write_entry(tmp_path, minimal_entry())
        ctx, _ = er.build_context(entry_path)
        assert "no public README reachable" in ctx

    def test_lists_existing_ids(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        write_entry(tmp_path, minimal_entry(id="osworld"))
        entry_path = write_entry(tmp_path, minimal_entry(id="fakebench"))
        ctx, _ = er.build_context(entry_path)
        assert "fakebench" in ctx
        assert "osworld" in ctx

    def test_includes_known_authors_when_listed(self, tmp_path, monkeypatch):
        (tmp_path / "known-authors.yaml").write_text(
            yaml.safe_dump({"fakebench": ["original_author_handle"]})
        )
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        entry_path = write_entry(tmp_path, minimal_entry())
        ctx, _ = er.build_context(entry_path)
        assert "original_author_handle" in ctx


# ── repo URL parsing ────────────────────────────────────────────────────────


class TestFetchRepoReadme:
    def test_returns_none_for_no_url(self):
        assert er.fetch_repo_readme(None) is None
        assert er.fetch_repo_readme("") is None

    def test_returns_none_for_non_github(self):
        assert er.fetch_repo_readme("git+https://gitlab.com/foo/bar") is None

    def test_extracts_owner_repo(self, monkeypatch):
        seen = []

        def fake_http(url, timeout=15):
            seen.append(url)
            if "main" in url:
                return "# Project README\n\nHello."
            return None

        monkeypatch.setattr(er, "http_get", fake_http)
        out = er.fetch_repo_readme(
            "git+https://github.com/example/fakebench-cube#subdirectory=cubes/fakebench-cube"
        )
        assert out is not None
        assert "Project README" in out
        assert "example/fakebench-cube/main/README.md" in seen[0]

    def test_falls_back_to_master_branch(self, monkeypatch):
        def fake_http(url, timeout=15):
            if "main" in url:
                return None
            if "master" in url:
                return "# legacy"
            return None

        monkeypatch.setattr(er, "http_get", fake_http)
        out = er.fetch_repo_readme("git+https://github.com/foo/bar")
        assert out == "# legacy"


# ── comment formatting ──────────────────────────────────────────────────────


class TestFormatVerdictComment:
    def test_pass_verdict_renders_all_pass(self):
        out = er.format_verdict_comment(good_verdict(), "fakebench")
        assert "## Entry review — `fakebench`" in out
        assert "**Verdict:** `PASS`" in out
        for k in er.CHECK_KEYS:
            assert k in out
        assert "✅ pass" in out

    def test_concern_verdict_shows_fail_icon(self):
        out = er.format_verdict_comment(concern_verdict(), "fakebench")
        assert "**Verdict:** `CONCERN`" in out
        assert "❌ fail" in out
        assert "famous benchmark" in out

    def test_unverified_renders_warn_icon(self):
        v = good_verdict()
        v["checks"]["wrapper_license_plausible"] = "unverified"
        out = er.format_verdict_comment(v, "fakebench")
        assert "⚠️ unverified" in out


# ── main(): wiring ──────────────────────────────────────────────────────────


class TestMain:
    def test_writes_verdict_and_comment_on_pass(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        monkeypatch.setattr(er, "call_claude", lambda sp, uc, m: good_verdict())
        entry_path = write_entry(tmp_path, minimal_entry())
        v_out = tmp_path / "verdict.json"
        c_out = tmp_path / "comment.md"
        rc = er.main(
            [
                "--entry", str(entry_path),
                "--verdict-out", str(v_out),
                "--comment-out", str(c_out),
            ]
        )
        assert rc == 0
        verdict = json.loads(v_out.read_text())
        assert verdict["verdict"] == "PASS"
        assert "**Verdict:** `PASS`" in c_out.read_text()

    def test_writes_concern_verdict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)
        monkeypatch.setattr(er, "call_claude", lambda sp, uc, m: concern_verdict())
        entry_path = write_entry(tmp_path, minimal_entry())
        v_out = tmp_path / "verdict.json"
        c_out = tmp_path / "comment.md"
        rc = er.main(
            [
                "--entry", str(entry_path),
                "--verdict-out", str(v_out),
                "--comment-out", str(c_out),
            ]
        )
        assert rc == 0
        assert json.loads(v_out.read_text())["verdict"] == "CONCERN"

    def test_missing_entry_returns_error(self, tmp_path, capsys):
        rc = er.main(
            [
                "--entry", str(tmp_path / "nope.yaml"),
                "--verdict-out", str(tmp_path / "v.json"),
                "--comment-out", str(tmp_path / "c.md"),
            ]
        )
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_dry_run_prints_context_no_api_call(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(er, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(er, "fetch_pypi", lambda pkg: None)
        monkeypatch.setattr(er, "fetch_repo_readme", lambda url: None)

        def boom(*a, **kw):
            raise AssertionError("call_claude must not run in --dry-run")

        monkeypatch.setattr(er, "call_claude", boom)
        entry_path = write_entry(tmp_path, minimal_entry())
        rc = er.main(
            [
                "--entry", str(entry_path),
                "--verdict-out", str(tmp_path / "v.json"),
                "--comment-out", str(tmp_path / "c.md"),
                "--dry-run",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "=== SYSTEM ===" in out
        assert "=== USER ===" in out


# ── verdict-tool schema sanity ──────────────────────────────────────────────


class TestVerdictToolSchema:
    def test_required_check_keys_match(self):
        schema_keys = set(er.VERDICT_TOOL["input_schema"]["properties"]["checks"]["required"])
        assert schema_keys == set(er.CHECK_KEYS)

    def test_verdict_enum_is_pass_or_concern(self):
        enum = er.VERDICT_TOOL["input_schema"]["properties"]["verdict"]["enum"]
        assert enum == ["PASS", "CONCERN"]
