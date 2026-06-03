#!/usr/bin/env python3
"""
generate.py — CUBE Registry static site generator.

Reads all entries/*.yaml, renders Jinja2 templates, writes to docs/.
Run by the generate-site GitHub Actions workflow on every push to main.

Usage:
  python site-src/generate.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ENTRIES_DIR = REPO_ROOT / "entries"
RESULTS_DIR = REPO_ROOT / "results"
TEMPLATES_DIR = SCRIPT_DIR / "templates"
DOCS_DIR = REPO_ROOT / "docs"

# Tag → colour mapping for chips
TAG_COLOURS: dict[str, str] = {
    "web": "bg-blue-100 text-blue-800",
    "coding": "bg-purple-100 text-purple-800",
    "os": "bg-gray-100 text-gray-800",
    "gui": "bg-green-100 text-green-800",
    "mobile": "bg-pink-100 text-pink-800",
    "science": "bg-yellow-100 text-yellow-800",
    "math": "bg-orange-100 text-orange-800",
    "multi-agent": "bg-indigo-100 text-indigo-800",
    "desktop": "bg-teal-100 text-teal-800",
    "multimodal": "bg-rose-100 text-rose-800",
    "nlp": "bg-cyan-100 text-cyan-800",
    "reasoning": "bg-violet-100 text-violet-800",
    "robotics": "bg-amber-100 text-amber-800",
    "games": "bg-lime-100 text-lime-800",
}

STATUS_BADGE: dict[str, dict[str, str]] = {
    "active": {"bg": "bg-green-100", "text": "text-green-800", "label": "Active"},
    "degraded": {"bg": "bg-yellow-100", "text": "text-yellow-800", "label": "Degraded"},
    "archived": {"bg": "bg-gray-100", "text": "text-gray-500", "label": "Archived"},
}


def load_entries() -> list[dict[str, Any]]:
    """Load all entries from entries/*.yaml, sorted by id."""
    entries = []
    for entry_path in sorted(ENTRIES_DIR.glob("*.yaml")):
        if entry_path.name == ".gitkeep":
            continue
        try:
            with open(entry_path) as f:
                entry = yaml.safe_load(f)
            if entry is None:
                continue
            # Attach the path for use in template rendering
            entry["_path"] = entry_path
            entries.append(entry)
        except Exception as e:
            print(f"Warning: failed to load {entry_path}: {e}")
    return entries


def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Add computed display fields to an entry dict."""
    e = dict(entry)

    # Raw YAML text (for the YAML viewer on the detail page)
    path = e.pop("_path", None)
    if path:
        try:
            e["_raw_yaml"] = Path(path).read_text()
        except Exception:
            e["_raw_yaml"] = ""
        e["_path"] = path
        # GitHub link to the YAML file (view + raw)
        try:
            rel = Path(path).relative_to(REPO_ROOT)
            e["_github_yaml_url"] = (
                f"https://github.com/The-AI-Alliance/cube-registry/blob/main/{rel}"
            )
            e["_github_raw_yaml_url"] = (
                f"https://raw.githubusercontent.com/The-AI-Alliance/cube-registry/main/{rel}"
            )
        except ValueError:
            e["_github_yaml_url"] = ""
            e["_github_raw_yaml_url"] = ""
    else:
        e["_raw_yaml"] = ""
        e["_github_yaml_url"] = ""
        e["_github_raw_yaml_url"] = ""

    # Status defaults
    status = e.get("status", "active") or "active"
    e["status"] = status
    e["status_badge"] = STATUS_BADGE.get(status, STATUS_BADGE["active"])

    # Tag chips
    tags = e.get("tags", []) or []
    e["tag_chips"] = [
        {"label": t, "cls": TAG_COLOURS.get(t, "bg-gray-100 text-gray-700")} for t in tags
    ]

    # Description truncated for card
    desc = e.get("description", "") or ""
    e["description_short"] = desc[:200].rstrip() + ("…" if len(desc) > 200 else "")

    # Features as sorted list of enabled flags
    features = e.get("features", {}) or {}
    e["features_list"] = sorted(k for k, v in features.items() if v)

    # Pip install command
    e["pip_install"] = f"pip install {e.get('package', '')}"

    # Legal
    legal = e.get("legal", {}) or {}
    e["legal"] = legal
    bench_lic = legal.get("benchmark_license", {}) or {}
    e["bench_license_reported"] = bench_lic.get("reported")
    e["bench_license_url"] = bench_lic.get("source_url")
    e["bench_license_verified"] = bench_lic.get("verified_by_original_authors", False)

    # Stress results
    e["has_stress_results"] = bool(e.get("stress_results_url"))

    return e


_GITHUB_RAW_BLOB = "https://github.com/The-AI-Alliance/cube-registry/blob/main"
_GITHUB_TREE = "https://github.com/The-AI-Alliance/cube-registry/tree/main"


def _json_for_html_script(data: Any) -> str:
    """Serialize *data* as JSON that's safe to drop inside ``<script>``.

    `json.dumps` does not escape ``<`` / ``>`` / ``&``, so a value like
    ``"</script><script>alert(1)</script>"`` would otherwise break out of
    the surrounding script element. Since community-submitted records land
    auto-merged on the live site, every free-text field is potentially
    attacker-controlled. Replace the dangerous bytes with their `\\uXXXX`
    JSON Unicode escapes — JSON.parse decodes them back on the browser side,
    but the HTML tokenizer never sees the raw markers.
    """
    return (
        json.dumps(data, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def load_results(entry: dict) -> list[dict[str, Any]]:
    """Load community-submitted results for *entry*, newest first.

    Returns a list of dicts ready for template rendering: the parsed JSON plus
    ``_submitter`` (GitHub handle from ``_submissions.json``), ``_date`` (ISO
    YYYY-MM-DD derived from evaluation_timestamp), and ``_detail_url`` (link
    to the raw JSON file on GitHub, which renders the full record).
    """
    cube_id = entry.get("id")
    if not cube_id:
        return []
    cube_results_dir = RESULTS_DIR / cube_id
    if not cube_results_dir.exists():
        return []

    submissions_path = cube_results_dir / "_submissions.json"
    submissions: dict[str, dict[str, str]] = {}
    if submissions_path.exists():
        try:
            data = json.loads(submissions_path.read_text())
            if isinstance(data, dict):
                submissions = data
        except json.JSONDecodeError:
            pass

    results: list[dict[str, Any]] = []
    for result_path in sorted(cube_results_dir.glob("*.json")):
        if result_path.name.startswith("_"):
            continue
        try:
            record = json.loads(result_path.read_text())
        except json.JSONDecodeError as e:
            # The PR-time validator should make this unreachable; warn loudly
            # so a corrupt file on main is visible at site-gen time (S8).
            print(f"Warning: failed to parse {result_path}: {e}")
            continue
        eid = record.get("evaluation_id", "")
        sub_meta = submissions.get(eid, {})
        record["_submitter"] = sub_meta.get("submitted_by", "—")
        ts = record.get("evaluation_timestamp")
        if isinstance(ts, (int, float)):
            record["_date"] = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            record["_date"] = "—"
        record["_detail_url"] = f"{_GITHUB_RAW_BLOB}/results/{cube_id}/{result_path.name}"
        results.append(record)

    # Newest first by evaluation_timestamp.
    results.sort(key=lambda r: r.get("evaluation_timestamp", 0), reverse=True)
    return results


def results_dir_url(cube_id: str) -> str:
    """GitHub directory URL used by the 'View all N submissions' link."""
    return f"{_GITHUB_TREE}/results/{cube_id}"


def load_stress_results(entry: dict) -> dict | None:
    """Load stress results JSON for an entry if available."""
    url = entry.get("stress_results_url")
    if not url:
        return None
    results_path = REPO_ROOT / url
    if not results_path.exists():
        return None
    try:
        with open(results_path) as f:
            return json.load(f)
    except Exception:
        return None


def build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    # Custom filters
    def format_bytes(value: float | None, unit: str = "GB") -> str:
        if value is None:
            return "—"
        return f"{value:.1f} {unit}"

    def format_ms(value: float | None) -> str:
        if value is None:
            return "—"
        if value < 1:
            return f"{value * 1000:.0f} ms"
        return f"{value:.2f} s"

    env.filters["format_bytes"] = format_bytes
    env.filters["format_ms"] = format_ms

    return env


def generate(dry_run: bool = False) -> None:
    """Generate the full static site."""
    entries_raw = load_entries()
    entries = [enrich_entry(e) for e in entries_raw]

    env = build_env()

    # Ensure docs/ exists
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(entries)

    # ── index.html ──────────────────────────────────────────────────────────
    index_tmpl = env.get_template("index.html.j2")
    # Collect all unique tags and features for filter bar
    all_tags = sorted({t for e in entries for t in (e.get("tags") or [])})
    all_features = sorted({f for e in entries for f in (e.get("features_list") or [])})
    all_infra = sorted({p for e in entries for p in (e.get("supported_infra") or [])})

    index_html = index_tmpl.render(
        entries=entries,
        all_tags=all_tags,
        all_features=all_features,
        all_infra=all_infra,
        generated_at=generated_at,
        total=total,
    )

    if not dry_run:
        (DOCS_DIR / "index.html").write_text(index_html)
        print(f"  Written: docs/index.html ({total} entries)")

    # ── Per-benchmark pages ──────────────────────────────────────────────────
    bench_tmpl = env.get_template("benchmark.html.j2")
    for entry in entries:
        benchmark_id = entry.get("id", "unknown")
        bench_dir = DOCS_DIR / benchmark_id
        if not dry_run:
            bench_dir.mkdir(parents=True, exist_ok=True)

        stress_data = load_stress_results(entry)
        all_results = load_results(entry)

        bench_html = bench_tmpl.render(
            entry=entry,
            stress_data=stress_data,
            results_data=all_results,
            results_count=len(all_results),
            results_dir_url=results_dir_url(benchmark_id),
            results_json=_json_for_html_script(all_results),
            generated_at=generated_at,
        )

        if not dry_run:
            (bench_dir / "index.html").write_text(bench_html)
            print(f"  Written: docs/{benchmark_id}/index.html")

    print(f"\nGenerated {total} benchmark pages in {DOCS_DIR}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate CUBE Registry static site.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and render but don't write files."
    )
    args = parser.parse_args()

    print("=== CUBE Registry Site Generator ===")
    generate(dry_run=args.dry_run)
    print("Done.")


if __name__ == "__main__":
    main()
