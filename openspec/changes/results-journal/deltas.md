# Deltas — Community results journal

Changes against [ci/spec.md](../../specs/ci/spec.md) and
[site/spec.md](../../specs/site/spec.md). Entry spec unchanged.

---

## ADDED — `results-check` workflow (ci spec)

**Insert after "Manual refresh".**

### Results check (every PR touching `results/`)

`results-check.yml` runs `scripts/results_check.py` against the PR. Activates only
when the diff includes added files under `results/`.

**Path isolation gate (precondition for auto-merge):**

| PR diff | Action |
|---|---|
| Only adds files under `results/<cube>/*.json` | Run validator → auto-merge if all pass |
| Touches anything else *in addition* | Validator runs informationally; fall back to standard human review |
| Modifies or deletes existing files under `results/` | Reject (journal is append-only) |

**Per-file validation** (all must pass):

1. JSON-schema validate against `results-schema.json`.
2. `<cube>` segment of the path matches an existing `entries/<cube>.yaml`.
3. JSON `benchmark_name` equals `<cube>`.
4. JSON `benchmark_version` is a known version (matches current entry, or a
   previously-seen version in `results/<cube>/`).
5. `benchmark_subset.n_tasks` ≤ `entries/<cube>.task_count`.
6. `outcomes` sum (`n_success + n_failure + n_max_steps + n_system_error + n_missing`)
   equals `benchmark_subset.n_tasks` (mutually exclusive, exhaustive).
7. `results.avg_score` is within metric bounds (default 0–1; per-cube override
   via optional entry field in a later RFC).
8. `agent.git_commit` is a 40-char lowercase hex string.
9. File size ≤ 50 KB.
10. `evaluation_id` is globally unique within `results/<cube>/`.
11. Filename equals the sanitized `{evaluation_id}.json`
    (`/` → `__`, charset enforced by schema).

On all-pass: apply `auto-merge` label → existing GitHub auto-merge merges the PR.
On any failure: post a comment listing the failing checks, do not label.

The runner has **no cloud credentials** and **does not import any benchmark
package** — validation is pure JSON schema + cross-reference + arithmetic.

---

## ADDED — Results journal (ci spec)

**Insert after "Results check" section.**

### Journal layout

```
results/
└── <cube-id>/
    └── <evaluation_id>.json     # one experiment-level run
```

One file per submitted run. Schema and example: `results-schema.json` +
`design.md` in this change folder.

Append-only. Files are never modified after merge. Mistakes are corrected by
appending a *new* submission with the corrected fields and a `supersedes`
reference to the original `evaluation_id`.

---

## ADDED — Results page (site spec)

**Insert after "Per-benchmark page".**

### Results section per benchmark

Each per-cube page gains a "Results" tab/section listing all entries in
`results/<cube-id>/`. V1 renders a sortable table:

| Date | Submitter | Agent | Model | Subset | Score | Outcomes (✓/✗/⏱/💥/–) | Cost (USD) | Provenance |
|---|---|---|---|---|---|---|---|---|

`Outcomes` cell renders the five-count breakdown
(`n_success/n_failure/n_max_steps/n_system_error/n_missing`) as small badges so
readers can distinguish "low score because hard" from "low score because the
runner crashed on most tasks."

`Provenance` cell links to the cube-harness commit (`agent.git_remote_url`).
`Submitter` is the GitHub handle of the PR author (recorded at merge time in a
`submissions.json` companion file, written by the merge workflow).

V2 (out of scope here): score-over-time, model comparison, filters.

---

## MODIFIED — Invariants (ci spec)

**Append:**

7. `results/` accepts community PRs and auto-merges them iff `results-check`
   passes *and* the diff is strictly inside `results/` (additions only). This is
   the single narrow exception to invariant #6.
8. The results-check runner has no cloud credentials and imports no benchmark
   packages.
9. `results/` is append-only: existing files are never modified or deleted by
   automation. Schema/format migrations land via tooling that writes *new* files.

**Reword invariant #6:**

> ~~Entries never auto-merge~~ → "Entry PRs never auto-merge — a maintainer reviews every
> PR. Results PRs auto-merge per invariant #7."

---

## MODIFIED — Pipeline overview (ci spec)

**Add to PR-opened branch:**

```
PR opened
 ├─ ownership-check
 ├─ quick-check
 └─ results-check     (only if PR adds files under results/)
                       └─ auto-merge (if path-isolated + all checks pass)
```

---

## MODIFIED — Workflow list (ci spec)

```
.github/workflows/{quick-check,slow-check,update-owners,generate-site,
                   periodic-health-check,manual-refresh,results-check}.yml
```

---

## NOT CHANGED

- All existing CI workflows and their security boundaries.
- Entry schema, ownership semantics, `OWNERS.yaml` write rules.
- `stress-results/`, `nightly-results/` (CI-bot-only write paths).
- The static site's index and per-benchmark page layout outside the new Results
  section.
