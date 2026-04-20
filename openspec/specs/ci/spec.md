# CI Pipeline

**Workflows:** `.github/workflows/{quick-check,slow-check,update-owners,generate-site,periodic-health-check,manual-refresh}.yml`
**Scripts:** `scripts/{ownership_check,quick_check,slow_check,health_check,update_owners}.py`

## Purpose

CI does the work a human reviewer would otherwise have to do: enforce ownership,
validate schema, run compliance, publish updates. A maintainer only approves and
merges; everything else is automated.

## Pipeline overview

```
PR opened
 ├─ ownership-check  (scripts/ownership_check.py, ~10s)  ─┐
 └─ quick-check      (scripts/quick_check.py, ~2 min)     ├─ both pass → ready-for-review label
                                                          │
maintainer reviews + merges                               │
 ├─ update-owners   (writes OWNERS.yaml via bot)
 ├─ generate-site   (site-src/generate.py → docs/)
 └─ slow-check      (async, real infra, ~5–30 min)

weekly cron
 └─ periodic-health-check  (PyPI availability + URL reachability)
```

## Ownership check (every PR)

Reads `OWNERS.yaml` from `origin/main` — never from the PR branch (prevents
self-granting).

| Situation | Result |
|-----------|--------|
| New entry (no key in `OWNERS.yaml`) | ✅ pass — open submission |
| Author modifying their own entry | ✅ pass |
| Stranger modifying someone else's entry | ❌ block |
| PR touches `OWNERS.yaml` or `stress-results/` directly | ❌ block |

GitHub handle format enforced: `^[a-zA-Z0-9][a-zA-Z0-9-]{0,37}$`.

## Quick compliance (every PR, Docker sandbox, ~2 min)

Runs with **no cloud credentials**. Safe to execute untrusted PyPI packages because
the Docker container is hardened:
`--cap-drop NET_ADMIN,SYS_PTRACE,SYS_ADMIN --security-opt no-new-privileges --pids-limit 512`.

Steps:
1. Validate YAML against `registry-schema.json`.
2. `pip install <package>==<version>` (falls back to `dev_install_url` if not yet on PyPI).
3. Import the package; resolve the `Benchmark` class via `cube.benchmarks` entry point.
4. Instantiate `Benchmark()`, call `get_task_configs()` → derive `task_count`.
5. Introspect `benchmark.resources` → serialize to YAML.
6. Inspect `Task` class for feature flags: `async`, `streaming`, `multi_agent`, `multi_dim_reward`.
7. Check for debug module: `has_debug_task`, `has_debug_agent`.
8. Write CI-derived fields back to the YAML in the PR branch.

On success: label `ready-for-review` + post a summary comment. No auto-merge.

## Slow compliance (post-merge, async)

Re-triggered when `version`, `package`, `supported_infra`, or any `image_url`
changes — NOT on tag/description/legal-only edits.

For each provider in `supported_infra`:
- Provision from `benchmark.resources` (Docker: runner; VM: ephemeral cloud spot).
- Run a full debug episode via `make_debug_agent()`.
- Capture profiling: setup time, step latency p50/p95, episode time.
- Write `stress-results/<id>/v<version>.json`.

On failure: open a GitHub issue tagging owners. The entry remains in the registry —
platforms decide which tier they require.

Cost: Docker checks free; VM checks ~$0.04–0.06/run (spot, ephemeral).

**Security boundary:** slow-check runner has cloud credentials but **never imports
the benchmark package** — the package runs inside the provisioned VM.

## Periodic health check (weekly)

Cron-triggered. Checks every entry:
- `pip install <package>` still succeeds
- URLs in `resources[].image_url` and `legal.benchmark_license.source_url` return HTTP 200

On failure: set `status: degraded`, open or update an issue tagging owners.

## Manual refresh

`manual-refresh.yml` is operator-triggered and runs the full suite
(ownership+quick+slow+health) over a named subset. Use when a security fix lands
or when re-validating after a cube-standard breaking change is resolved.

## update-owners (post-merge, CI bot)

Writes `OWNERS.yaml`. The repository has a path-restricted bypass rule: only the
CI bot can push changes to `OWNERS.yaml`. Humans are blocked.

On merge:
- For a new entry: add `id: [author_handles]`
- For an updated entry: no change unless `authors` changed

## generate-site (post-merge)

Runs `site-src/generate.py` → writes `docs/`. Commit via CI bot. See
[site spec](../site/spec.md).

## Invariants

1. Ownership check reads `origin/main`, never the PR branch.
2. Quick-check runs in a Docker sandbox without cloud credentials.
3. Slow-check never imports the benchmark package in the runner.
4. `OWNERS.yaml` is writable only by the CI bot.
5. `stress-results/` is writable only by the CI bot.
6. Entries never auto-merge — a maintainer reviews every PR.

## Gotchas

- PyPI install caches are per-run — quick-check is not fast because of caching; it
  reinstalls fresh each PR.
- `dev_install_url` packages bypass PyPI — the package source is cloned and
  installed via `pip install git+...`. Health-check still requires PyPI for long-term
  availability signaling.
- A package that's valid at quick-check but goes offline later flips to `degraded`
  at the next health-check cycle — not immediately.
