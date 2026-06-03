"""Unit tests for scripts/record_submitter.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import record_submitter as rs  # noqa: E402


@pytest.fixture
def staged_repo(tmp_path, monkeypatch) -> Path:
    (tmp_path / "results").mkdir()
    monkeypatch.setattr(rs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rs, "RESULTS_DIR", tmp_path / "results")
    return tmp_path


def _write_result(repo: Path, cube_id: str, eid: str) -> Path:
    cube_dir = repo / "results" / cube_id
    cube_dir.mkdir(parents=True, exist_ok=True)
    path = cube_dir / (eid.replace("/", "__") + ".json")
    path.write_text(json.dumps({"evaluation_id": eid}))
    return path


def test_appends_new_entry(staged_repo, monkeypatch):
    path = _write_result(staged_repo, "miniwob", "alacoste/run1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_submitter.py",
            "--author",
            "alacoste",
            "--merge-timestamp",
            "2026-05-29T20:00:00Z",
            "--files",
            str(path),
        ],
    )
    assert rs.main() == 0
    subs_path = staged_repo / "results" / "miniwob" / "_submissions.json"
    submissions = json.loads(subs_path.read_text())
    assert submissions == {
        "alacoste/run1": {"submitted_by": "alacoste", "merged_at": "2026-05-29T20:00:00Z"}
    }


def test_appends_to_existing_file(staged_repo, monkeypatch):
    cube_dir = staged_repo / "results" / "miniwob"
    cube_dir.mkdir(parents=True)
    (cube_dir / "_submissions.json").write_text(
        json.dumps({"older/run": {"submitted_by": "older", "merged_at": "2026-01-01T00:00:00Z"}})
    )
    path = _write_result(staged_repo, "miniwob", "alacoste/run2")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_submitter.py",
            "--author",
            "alacoste",
            "--merge-timestamp",
            "2026-05-29T20:00:00Z",
            "--files",
            str(path),
        ],
    )
    assert rs.main() == 0
    submissions = json.loads((cube_dir / "_submissions.json").read_text())
    assert set(submissions) == {"older/run", "alacoste/run2"}


def test_skips_bookkeeping_files(staged_repo, monkeypatch):
    cube_dir = staged_repo / "results" / "miniwob"
    cube_dir.mkdir(parents=True)
    bookkeeping = cube_dir / "_submissions.json"
    bookkeeping.write_text("{}")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_submitter.py",
            "--author",
            "alacoste",
            "--merge-timestamp",
            "2026-05-29T20:00:00Z",
            "--files",
            str(bookkeeping),
        ],
    )
    assert rs.main() == 0
    assert bookkeeping.read_text() == "{}"  # untouched
