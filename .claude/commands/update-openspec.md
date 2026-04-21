# Update OpenSpec

Audit `openspec/specs/` against the current source code and update specs that have drifted.

## When to use

Run this after any PR that changes CI logic, the entry schema, or site generation.

## Instructions

For each layer listed below, read the source file(s) and the corresponding spec, then identify drift:

| Layer | Source | Spec |
|-------|--------|------|
| Entry schema | `registry-schema.json`, `entries/*.yaml` (sample) | `openspec/specs/entry/spec.md` |
| CI pipeline | `scripts/quick_check.py`, `scripts/slow_check.py`, `scripts/ownership_check.py`, `scripts/health_check.py` | `openspec/specs/ci/spec.md` |
| Site generation | `site-src/generate.py`, `site-src/templates/` | `openspec/specs/site/spec.md` |

## What counts as drift

- New schema field added or removed from `registry-schema.json`
- CI check added, removed, or its pass/fail conditions changed
- Security boundary relaxed or tightened (always flag these explicitly)
- Site template structure changed in a way that affects the output contract

## Decision rule

**Minor drift** (1–3 spec lines, no security boundary change): edit the spec directly.

**Substantive drift** (new CI stage, schema breaking change, security boundary change):
create `openspec/changes/<name>/` with `proposal.md` + `deltas.md` (ADDED / MODIFIED / REMOVED
sections in target-state language) before editing the spec.

Security boundary changes MUST go through a change proposal with explicit threat-model notes —
never edit `openspec/specs/ci/spec.md` security invariants directly.

## Output

Report per-layer: `OK`, `UPDATED`, or `CHANGE PROPOSED`. Show diffs for every change made.
If no drift found, say so — don't open a PR for a no-op.
