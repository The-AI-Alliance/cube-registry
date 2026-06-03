# Deltas: Auto-merge entries via LLM-reviewed CI

## `openspec/specs/ci/spec.md`

### Pipeline overview

**Before**:
```
PR opened
 ├─ ownership-check  (scripts/ownership_check.py, ~10s)  ─┐
 └─ quick-check      (scripts/quick_check.py, ~2 min)     ├─ both pass → ready-for-review label

maintainer reviews + merges
 ├─ update-owners
 ├─ generate-site
 └─ slow-check (async, post-merge)
```

**After (Phase 1)**:
```
PR opened
 ├─ ownership-check  (~10s)                              ─┐
 ├─ quick-check      (~2 min)                            ─┤
 └─ entry-review     (Claude action, ~1 min)              ├─ all pass + verdict PASS → auto-merge
                                                          ├─ verdict CONCERN → ready-for-review (manual)
                                                          │
post-merge:
 ├─ update-owners
 ├─ generate-site
 └─ slow-check (async, post-merge)
```

### New section: `## Entry review (every PR touching entries/*.yaml)`

Runs after ownership + quick checks pass. Invokes Claude with a checked-in
prompt (`scripts/entry_review_prompt.md`) plus the entry YAML, the package's
PyPI page + README, the linked repo (if `dev_install_url` is set), and the
existing `entries/` directory + `known-authors.yaml` for cross-reference.

Returns structured verdict:

```yaml
verdict: PASS | CONCERN
checks:
  description_matches_package: pass | fail | unverified
  authors_consistent_with_git:  pass | fail | unverified
  no_id_squat_vs_existing:      pass | fail | unverified
  no_brand_impersonation:       pass | fail | unverified
  wrapper_license_plausible:    pass | fail | unverified
notes: <freeform>
```

**Triggers auto-merge when all of:**

- ownership-check ✅
- quick-compliance ✅
- entry-review verdict = `PASS` (explicit; defaults are NOT merge-permissive)
- PR diff is strictly additions/modifications under `entries/<id>.yaml`
  for an id the submitter owns (or a brand-new id)

**On `CONCERN`**: post review as PR comment, apply `human-review-needed`,
do NOT merge.

**Security boundary**: review job runs with read-only `pull_request`
permissions. Merge happens in a separate job that consumes the verdict —
compromising the LLM step alone does not bypass ownership / schema / install
checks (separate jobs).

### Invariants

**Invariant #6 changes from**:

> 6. Entries never auto-merge — a maintainer reviews every PR.

**To**:

> 6. Entries auto-merge iff (ownership-check ∧ quick-compliance ∧
>    entry-review verdict=PASS) AND the diff is strictly
>    additions/modifications under `entries/<id>.yaml`. Any deviation
>    falls back to `ready-for-review` + manual merge.

## `openspec/specs/entry/spec.md`

### `## Contracts for submitters`

**Add bullet**:

> - On submission, an LLM reviewer checks that the entry's description matches
>   the package, the GitHub handles in `authors[]` are plausibly tied to the
>   linked repo's commit history, the wrapper license is consistent with the
>   source, and the `id`/`name` doesn't collide with or impersonate an existing
>   entry. PRs that fail any of these are labeled `human-review-needed` and
>   held for a maintainer.

## `README.md`

### "Submission steps" section

Replace the auto-merge promise that PR #50 already softened with the actual
Phase-1 behavior:

> Either way, CI validates the entry. On all checks green, including the LLM
> semantic-review verdict, the PR auto-merges. PRs flagged `human-review-needed`
> are held for a maintainer.

## `.github/pull_request_template.md`

### "What CI will check" section

Add a row:

| Check | When | ~Time |
|---|---|---|
| LLM semantic review (Claude) | On PR (after ownership + quick) | ~1 min |

### Below the table

Replace the "ready-for-review" copy with:

> When ownership-check, quick-compliance, and the LLM review verdict all
> pass, the PR auto-merges. A `human-review-needed` label means the LLM
> reviewer surfaced a concern; a maintainer will follow up.
