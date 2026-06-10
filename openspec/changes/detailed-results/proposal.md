# Detailed per-task results bundle

## Problem
The journal stores **aggregates only** — one small summary record per run. That's
enough for the UI table and drift detection, but it can't be independently
checked: the headline `avg_score` is self-reported and unverifiable, and
downstream consumers (e.g. ATLAS) have no per-task data. The existing
`instance_results_url` punts detail to an *external* host, which fragments the
journal and isn't auto-validated.

## Change
Let a submission carry its per-task data **in-repo**, next to the summary, as a
single gzipped JSONL bundle the verifier checks:

- **Summary** `results/<cube>/<id>.json` — unchanged shape, stays under the 50 KB
  cap (drives the UI). Gains an optional `detailed_results` pointer
  `{file, format, sha256, n_samples}`.
- **Bundle** `results/<cube>/<id>.samples.jsonl.gz` — one eval-level row per task
  (`samples-schema.json`; no trajectory blobs). Own 20 MB cap.
- **Verifier** (`results_check.py`): when `detailed_results` is present, decompress
  the bundle, line-validate each row, re-check the sha256, and **re-derive
  `results.avg_score` from the per-task scores** — rejecting any summary whose
  headline its own samples don't support. Orphan bundles (no referencing summary)
  are rejected.

`detailed_results` is optional: aggregate-only submissions keep working.

## Boundary impact (threat model)
Auto-merge path-isolation widens from `results/<cube>/*.json` to also accept
`results/<cube>/*.samples.jsonl.gz`. The bundle is **never trusted blindly**: it
is auto-merge-eligible only when a summary references it *and* it passes sha256 +
schema + consistency + size + orphan checks. The append-only and "nothing outside
results/" boundaries are unchanged (a bundle is an addition under `results/`).
Net: this *strengthens* validation (aggregates become verifiable) while only
admitting one new, fully-validated file type.

## Alternatives
- Keep `instance_results_url` (external host) — fragments the journal, no
  auto-validation, friction. Retained for >20 MB cases.
- Inline per-task JSON in the summary — blows the 50 KB cap and the UI table.
