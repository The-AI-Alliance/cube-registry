"""Entry review — LLM-based semantic check for cube-registry entry PRs.

Loads the entry YAML, gathers evidence (PyPI metadata, linked repo's README,
existing registry entries, known-authors), calls Claude with a structured
tool that returns a verdict, and writes the verdict to a JSON file the
workflow's auto-merge job consumes.

The verdict shape (enforced by tool schema):

    {
      "verdict": "PASS" | "CONCERN",
      "checks": {
        "description_matches_package":  "pass" | "fail" | "unverified",
        "authors_consistent_with_git":  "pass" | "fail" | "unverified",
        "no_id_squat_vs_existing":      "pass" | "fail" | "unverified",
        "no_brand_impersonation":       "pass" | "fail" | "unverified",
        "wrapper_license_plausible":    "pass" | "fail" | "unverified"
      },
      "notes": "<freeform>"
    }

Exits 0 always (verdict semantics are in the JSON, not the exit code) so the
workflow can post the verdict regardless of PASS/CONCERN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MODEL = "claude-opus-4-8"
PROMPT_PATH = Path(__file__).parent / "entry_review_prompt.md"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

CHECK_KEYS = [
    "description_matches_package",
    "authors_consistent_with_git",
    "no_id_squat_vs_existing",
    "no_brand_impersonation",
    "wrapper_license_plausible",
]

VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Submit the structured review verdict. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "CONCERN"]},
            "checks": {
                "type": "object",
                "properties": {
                    k: {"type": "string", "enum": ["pass", "fail", "unverified"]}
                    for k in CHECK_KEYS
                },
                "required": CHECK_KEYS,
                "additionalProperties": False,
            },
            "notes": {"type": "string"},
        },
        "required": ["verdict", "checks", "notes"],
        "additionalProperties": False,
    },
}


def http_get(url: str, timeout: int = 15) -> str | None:
    """GET text from a URL. None on any failure (404, network, etc.)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cube-registry-bot"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def fetch_pypi(package: str) -> dict[str, Any] | None:
    """Fetch PyPI metadata for a package. Returns the JSON dict or None."""
    body = http_get(f"https://pypi.org/pypi/{package}/json")
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def fetch_repo_readme(dev_install_url: str | None) -> str | None:
    """Extract the README.md from a github/gitlab dev_install_url, if any.

    dev_install_url shape: 'git+https://github.com/<owner>/<repo>#subdirectory=...'
    """
    if not dev_install_url:
        return None
    m = re.match(r"git\+https://github\.com/([^/]+)/([^/#]+)", dev_install_url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2).rstrip(".git")
    for branch in ("main", "master"):
        body = http_get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md")
        if body:
            return body[:8000]
    return None


def load_existing_entry_ids() -> list[str]:
    """List ids of currently-registered entries (for squat / impersonation check)."""
    entries_dir = REPO_ROOT / "entries"
    if not entries_dir.is_dir():
        return []
    return sorted(p.stem for p in entries_dir.glob("*.yaml"))


def load_known_authors() -> dict[str, list[str]]:
    """Load known-authors.yaml mapping (id → list of original-author github handles)."""
    path = REPO_ROOT / "known-authors.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data if isinstance(data, dict) else {}


def build_context(entry_path: Path) -> tuple[str, dict[str, Any]]:
    """Assemble the evidence block sent to the model. Returns (text, raw_entry_dict)."""
    entry = yaml.safe_load(entry_path.read_text())
    package = entry.get("package", "")
    dev_install_url = entry.get("dev_install_url")

    pypi_data = fetch_pypi(package) if package else None
    pypi_info = pypi_data.get("info", {}) if pypi_data else {}
    pypi_description = (pypi_info.get("description") or "")[:6000]
    pypi_license = pypi_info.get("license") or ""
    pypi_summary = pypi_info.get("summary") or ""

    readme = fetch_repo_readme(dev_install_url) or "(no public README reachable)"
    existing_ids = load_existing_entry_ids()
    known_authors = load_known_authors()
    known_for_id = known_authors.get(entry.get("id", ""), [])

    parts = [
        "## ENTRY UNDER REVIEW",
        "```yaml",
        entry_path.read_text(),
        "```",
        "",
        "## PYPI METADATA",
        f"Package: `{package}`",
        f"Summary (from PyPI): {pypi_summary or '(empty)'}",
        f"License field (from PyPI): {pypi_license or '(empty)'}",
        "",
        "PyPI long description (first 6KB):",
        "```",
        pypi_description or "(no description on PyPI — package may be unpublished)",
        "```",
        "",
        "## LINKED REPO README (first 8KB)",
        "```",
        readme,
        "```",
        "",
        "## EXISTING REGISTRY ENTRY IDS",
        ", ".join(existing_ids) or "(none)",
        "",
        "## KNOWN ORIGINAL AUTHORS FOR THIS ID",
        f"From known-authors.yaml: {known_for_id or '(not listed)'}",
        "",
        "Call `submit_verdict` exactly once with your review.",
    ]
    return "\n".join(parts), entry


def call_claude(system_prompt: str, user_content: str, model: str) -> dict[str, Any]:
    """Invoke Anthropic API with a forced tool call. Returns the verdict dict.

    Imports `anthropic` lazily so the script can be imported in tests that
    monkeypatch this function without the SDK installed.
    """
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "submit_verdict"},
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_verdict":
            return dict(block.input)
    raise RuntimeError("Model did not call submit_verdict")


def format_verdict_comment(verdict: dict[str, Any], entry_id: str) -> str:
    """Render a Markdown PR comment summarizing the verdict."""
    icon = {"pass": "✅", "fail": "❌", "unverified": "⚠️"}
    lines = [
        f"## Entry review — `{entry_id}`",
        "",
        f"**Verdict:** `{verdict['verdict']}`",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for k in CHECK_KEYS:
        v = verdict["checks"][k]
        lines.append(f"| `{k}` | {icon.get(v, '?')} {v} |")
    if verdict.get("notes"):
        lines.append("")
        lines.append("**Notes:**")
        lines.append("")
        lines.append(verdict["notes"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", required=True, help="Path to entries/<id>.yaml")
    parser.add_argument(
        "--verdict-out",
        required=True,
        help="Path to write verdict JSON (consumed by auto-merge job)",
    )
    parser.add_argument(
        "--comment-out",
        required=True,
        help="Path to write the Markdown PR comment",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("ENTRY_REVIEW_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled context and exit (no API call)",
    )
    args = parser.parse_args(argv)

    entry_path = Path(args.entry)
    if not entry_path.is_file():
        print(f"error: entry file not found: {entry_path}", file=sys.stderr)
        return 1

    system_prompt = PROMPT_PATH.read_text()
    user_content, entry = build_context(entry_path)

    if args.dry_run:
        print("=== SYSTEM ===")
        print(system_prompt)
        print("=== USER ===")
        print(user_content)
        return 0

    verdict = call_claude(system_prompt, user_content, args.model)

    Path(args.verdict_out).write_text(json.dumps(verdict, indent=2))
    Path(args.comment_out).write_text(format_verdict_comment(verdict, entry.get("id", "")))
    print(f"Verdict: {verdict['verdict']}")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
