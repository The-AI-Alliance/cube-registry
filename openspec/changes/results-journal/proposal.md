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
   (benchmark + version + subset name/filter + `n_tasks` denominator) and
   *what happened* (avg score + std err + mutually-exclusive outcome counts:
   `n_success`, `n_failure`, `n_max_steps`, `n_system_error`, `n_missing` —
   summing to `n_tasks`). No per-task data — submitters keep raw trajectories
   on their own infra; this is the journal, not the archive.
2. New workflow `results-check.yml` validates each added file and **auto-merges
   the PR** when (and only when) every check passes and the diff is strictly
   inside `results/`.
3. Per-cube results table rendered into the existing static site.
4. New `results-schema.json` (cube-native shape, not EEE-shaped — see "Not in
   scope").

## Why auto-merge

Auto-merge is the load-bearing decision. Without it, every submission burns
maintainer attention and the journal stays empty. The validator (see `design.md`)
catches structural problems, cross-references the registry, and rejects anything
implausible — exactly the work a human reviewer would do for a results PR. A
maintainer's judgment adds no signal here.

This relaxes CI Invariant #6 ("entries never auto-merge") *narrowly*: it applies
only when the diff touches **only** `results/*.json` and only adds files. Any
deviation falls back to standard human review.

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
`EvalLog` from an experiment dir, builds the JSON, and opens a PR via `gh`.
That ships separately in cube-harness; this proposal only specifies the
registry-side contract (schema + workflow + site).

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

| Phase | Deliverable |
|-------|-------------|
| 1 (this PR) | Proposal + deltas + design |
| 2 | `results-schema.json`, `scripts/results_check.py`, `results-check.yml`, fixtures, tests |
| 3 | Site template + `generate.py` update; first sample entry |
| 4 | `submit_to_journal.py` in cube-harness |
| 5 (later) | V2 charts; verified-flag bot |
