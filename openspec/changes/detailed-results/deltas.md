# Deltas

## results-schema.json — MODIFIED
- ADDED optional top-level `detailed_results` object
  `{file: <stem>.samples.jsonl.gz, format: "jsonl.gz", sha256: <hex64>, n_samples: int}`
  (`additionalProperties: false`). `instance_results_url` description updated to
  prefer `detailed_results` for in-repo bundles.

## samples-schema.json — ADDED
- New schema for ONE bundle row (per task/episode). `required: [sample_id, score]`,
  `additionalProperties: true` (lenient — the registry pins only what it verifies).

## scripts/results_check.py — MODIFIED
- `check_bundle()`: validates the referenced bundle (stem match, presence, 20 MB
  cap, sha256, per-line samples-schema, `n_samples`, and `avg_score` consistency).
- `check_file()`: runs `check_bundle` when `detailed_results` is present.
- `main()`: partitions added `.json` vs `.samples.jsonl.gz`; rejects orphan bundles.
- New caps: `MAX_BUNDLE_SIZE_BYTES = 20 MB` (summary's 50 KB cap unchanged).

## .github/workflows/results-check.yml — MODIFIED
- Added-files filter also collects `results/*/*.samples.jsonl.gz` so the orphan
  check sees bundles. Auto-merge eligibility logic unchanged.

## CI invariant (results path-isolation) — MODIFIED
- Auto-merge accepts strictly additions under `results/<cube>/` of `*.json`
  **or** `*.samples.jsonl.gz`; the `.gz` is eligible only if validated via a
  referencing summary. Append-only + no-non-results-paths unchanged.
