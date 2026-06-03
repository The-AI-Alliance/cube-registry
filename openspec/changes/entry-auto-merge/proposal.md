# Proposal: Auto-merge entries via LLM-reviewed CI

## Context

README and PR template promise auto-merge for entries. The actual workflow
labels `ready-for-review` and waits for a maintainer click. CI spec invariant
#6 codifies the manual-review rule on the grounds that a buggy or
compromised quick-check could rubber-stamp anything.

The security argument addresses the wrong threat model. The threats auto-merge
exposes are **semantic**, not install-time:

| Threat | Catchable by `pip install` + `Benchmark` import? |
|---|---|
| Malicious code at install | ✅ (hardened sandbox catches outbound calls in import) |
| Privilege escalation via `OWNERS.yaml` | ✅ (ownership-check reads `origin/main`) |
| id-squatting | ❌ |
| Brand impersonation | ❌ |
| Author-handle impersonation | ❌ |
| Description deception (entry text doesn't match package) | ❌ |
| Legal misrepresentation (wrong SPDX, stolen content) | ❌ |
| Sophisticated supply-chain backdoor in PyPI release | ❌ (same for manual review) |

A maintainer eyeballing a YAML for 30 seconds doesn't catch a supply-chain
backdoor either — so the bar for "what manual review buys" is the semantic
checks. Those are exactly what an LLM reviewer with structured output is
good at. As the registry scales, manual review degrades to rubber-stamping
anyway, and rubber-stamped human review is strictly worse than structured
automated review.

## What

A new workflow `entry-review.yml` runs after ownership + quick-check pass on
any PR touching `entries/*.yaml`. It invokes a Claude action with a checked-in
prompt (`scripts/entry_review_prompt.md`) that returns a structured verdict:

```yaml
verdict: PASS | CONCERN
checks:
  description_matches_package: pass | fail | unverified
  authors_consistent_with_git: pass | fail | unverified
  no_id_squat_vs_existing: pass | fail | unverified
  no_brand_impersonation: pass | fail | unverified
  wrapper_license_plausible: pass | fail | unverified
notes: <freeform>
```

The reviewer reads: the entry YAML, the package's PyPI page + README, the
linked repo (`dev_install_url` if present) including `git log` of the cube
subdirectory, the existing `entries/` and `known-authors.yaml` for cross-reference.

**Auto-merge fires when all of:**

- `ownership-check` ✅
- `quick-compliance` ✅
- `entry-review` verdict = `PASS` (explicit positive, not absence-of-failure)
- PR diff is strictly additions / modifications under `entries/<id>.yaml`
  for an id the submitter owns (or a brand-new id)

On `CONCERN`: post the review as a PR comment, apply `human-review-needed`,
do NOT merge. On any check `unverified`: surfaces in `notes`; verdict is up
to the reviewer.

## What stays manual

- `OWNERS.yaml` edits (already CI-bot-only)
- Workflow / script / spec changes
- Any PR touching files outside `entries/`
- Verdict = `CONCERN` (label-gated)

## Threat model deltas

- Review prompt is checked into the repo — diffable, auditable, blameable.
- Verdict defaults to NOT merge-permissive (`PASS` must be explicit).
- The LLM step runs in a separate job from ownership/schema/install — compromising
  one doesn't compromise the others.
- Action runs under read-only `pull_request` permissions; merge happens in a
  follow-up job that requires the verdict.
- Cost: ~$0.50–3 per PR with Opus. At low hundreds of submissions / year, modest.

## Phasing

| Phase | Scope | PR scope |
|---|---|---|
| 0 | Doc-truth fix: stop promising auto-merge until it exists | PR #50 (this PR) |
| 1 | `entry-review.yml` + auto-merge gated on `ownership ∧ quick ∧ review=PASS` | Follow-up registry PR |
| 2 | Slow-check moved pre-merge with `/ok-to-test` label-gate for fork PRs | Later registry PR |
| 3 | Per-cube `review_overrides` (e.g. cubes with unusual provenance) | Later, optional |

Phase 1 doesn't lower the bar from today's manual review (which also only
sees quick-check pass before merge). It removes the human-click step and adds
the semantic-checks the human wasn't catching anyway.

Phase 2 is independently valuable but bigger — fork PRs running cloud-infra
jobs is a known abuse vector, so it needs a label-gate.

## Not in scope (handled in cube-standard)

- `cube registry add` rerun-overwrites-edits fix
- Post-submit CLI guidance ("a maintainer will merge…" → "auto-merging on green…")
