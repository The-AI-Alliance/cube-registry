# CI Pipeline

**Workflows:** `.github/workflows/{quick-check,slow-check,update-owners,generate-site,periodic-health-check,manual-refresh}.yml`
**Scripts:** `scripts/{ownership_check,quick_check,slow_check,health_check,update_owners}.py`

## Purpose

CI does the work a human reviewer would otherwise have to do: enforce ownership,
validate schema, run compliance, publish updates. A maintainer only approves and
merges; everything else is automated.

## Pipeline overview

```
PR opened (entries/*.yaml)
 ├─ ownership-check  (scripts/ownership_check.py, ~10s)
 ├─ quick-compliance (scripts/quick_check.py, ~2 min, Docker sandbox)
 ├─ slow-compliance  (scripts/slow_check.py --provider local, ~5 min)
 └─ entry-review     (scripts/entry_review.py, Claude, ~1 min)
                          ↳ verdict PASS + path-isolated + same-repo → auto-merge
                          ↳ everything else → ready-for-review (manual)

post-merge (push to main)
 ├─ update-owners   (writes OWNERS.yaml via bot)
 ├─ generate-site   (site-src/generate.py → docs/)
 └─ slow-check      (cloud-VM stress run on supported_infra → stress-results/)

weekly cron
 └─ periodic-health-check  (PyPI availability + URL reachability)
```

The pre-merge slow-compliance runs the debug task on the runner (provider
`local`) — fast gate, no cloud spend. The post-merge slow-check is the full
stress run across `supported_infra` (cloud providers) that writes
`stress-results/<id>/v<version>.json`. Drift is caught by the weekly
health-check.

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

On success: trigger the slow-compliance + entry-review gates below. On
failure: PR shows the check failure; submitter fixes and pushes.

## Slow compliance (PR-time, `provider: local`, ~5 min)

Runs the debug task on the GitHub-Actions runner — no cloud credentials, no
VM provisioning. Treats failure as a hard gate: auto-merge cannot fire if
the cube can't complete a single debug episode. For benchmarks whose `local`
provider isn't supported (no Docker support, GPU-only, etc.), this step
short-circuits to `ready-for-review` and a maintainer reviews manually.

## Entry review (PR-time, ~1 min)

LLM-based semantic check. Runs `scripts/entry_review.py` against the entry,
its PyPI metadata, the linked repo's README, and the existing `entries/` +
`known-authors.yaml`. The script invokes Claude with a forced tool call to
return a structured verdict:

```yaml
verdict: PASS | CONCERN
checks:
  description_matches_package: pass | fail | unverified
  authors_consistent_with_git: pass | fail | unverified
  no_id_squat_vs_existing:     pass | fail | unverified
  no_brand_impersonation:      pass | fail | unverified
  wrapper_license_plausible:   pass | fail | unverified
notes: <freeform>
```

If `ANTHROPIC_API_KEY` is not set in repo secrets the step graceful-degrades
to `verdict=UNKNOWN` → routes to `ready-for-review` (today's behaviour). This
lets the workflow ship and the secret get added when ready.

## Auto-merge (when all gates pass)

Fires when **all** of:

- ownership-check ✅
- quick-compliance ✅
- slow-compliance ✅
- entry-review verdict = `PASS`
- PR diff is strictly additions/modifications under `entries/<id>.yaml`
  (no deletes, no other paths touched — `path_isolated == true`)
- PR is from the same repo (fork PRs can't `gh pr merge` with the default
  GITHUB_TOKEN; they fall back to manual merge)

On firing: applies `auto-merge` label, calls `gh pr merge --auto --squash`.

## Request human review (fallback)

Fires when auto-merge can't — verdict ≠ PASS (CONCERN or UNKNOWN), path not
isolated, or PR from a fork. Applies `ready-for-review` label, posts a
summary listing the specific reasons. Maintainer completes the merge.

## Slow compliance (post-merge, cloud VMs, async)

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
6. Entries auto-merge iff (ownership-check ∧ quick-compliance ∧
   slow-compliance ∧ entry-review verdict=PASS) AND the diff is strictly
   additions/modifications under `entries/<id>.yaml` AND the PR is from the
   same repo. Any deviation falls back to `ready-for-review` + manual merge.
7. The entry-review prompt lives at `scripts/entry_review_prompt.md` —
   checked into the repo, diffable, auditable. The Claude action runs in a
   separate job from ownership/schema/install/slow-check; compromising the
   LLM step alone does not bypass the other gates.

## Gotchas

- PyPI install caches are per-run — quick-check is not fast because of caching; it
  reinstalls fresh each PR.
- `dev_install_url` packages bypass PyPI — the package source is cloned and
  installed via `pip install git+...`. Health-check still requires PyPI for long-term
  availability signaling.
- A package that's valid at quick-check but goes offline later flips to `degraded`
  at the next health-check cycle — not immediately.
