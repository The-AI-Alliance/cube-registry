# Registry Entry

**Schema:** `registry-schema.json` (JSON Schema Draft 7)
**Files:** `entries/<id>.yaml`

## Purpose

One YAML file per benchmark in `entries/`. Split into author-provided fields (from
the PR) and CI-derived fields (written by compliance checks after merge). The
filename matches `id` — both must be globally unique.

## Fields

### Author-provided (in the PR)

| Field | Required | Notes |
|-------|----------|-------|
| `id` | ✅ | Unique slug matching filename (`osworld`, `webarena-lite`) |
| `name` | ✅ | Human-readable display name |
| `version` | ✅ | Must match PyPI package version exactly |
| `description` | ✅ | One-paragraph summary |
| `package` | ✅ | PyPI package name (validated against PyPI normalization) |
| `dev_install_url` | — | `git+https://github.com/…` or `git+https://gitlab.com/…` for pre-PyPI packages |
| `authors[].github` | ✅ | GitHub handle; validated against `^[a-zA-Z0-9][a-zA-Z0-9-]{0,37}$`; populates `OWNERS.yaml` on merge |
| `authors[].name` | — | Display name |
| `legal.wrapper_license` | ✅ | SPDX identifier for the cube wrapper code |
| `legal.benchmark_license.reported` | — | SPDX id as reported by the cube developer (unverified) |
| `legal.benchmark_license.source_url` | — | Link to the upstream license — health-checked |
| `legal.notices[]` | — | Structured notices: `third_party_data`, `software_registration`, `live_website_clone`, `attribution` |
| `tags` | — | `web`, `coding`, `os`, `gui`, `mobile`, `science`, `math`, `multi-agent` |
| `paper` | — | arXiv or venue URL |
| `getting_started_url` | — | Docs or quick-start |
| `supported_infra` | — | `aws`, `azure`, `gcp`, `local`. Defaults to `[aws]` |
| `max_concurrent_tasks` | — | Parallelism hint |
| `parallelization_mode` | — | `sequential \| task-parallel \| benchmark-parallel` |

### CI-derived (written by quick or slow check — do not edit)

| Field | Set by | Notes |
|-------|--------|-------|
| `status` | health-check | `active \| degraded \| archived` |
| `task_count` | quick-check | From `benchmark.get_task_configs()` |
| `has_debug_task` | quick-check | Required `true` for slow check to run |
| `has_debug_agent` | quick-check | From `make_debug_agent()` presence |
| `resources` | quick-check | Serialized `ResourceConfig` objects from `benchmark.resources` |
| `action_space` | quick-check | Tool names from a reset task |
| `features.*` | quick-check | `async`, `streaming`, `multi_agent`, `multi_dim_reward` |
| `legal.benchmark_license.verified_by_original_authors` | quick-check | `true` if submitter is in `known-authors.yaml` |
| `stress_results_url` | slow-check | Path to latest profiling results JSON |

## Invariants

1. `id` matches `<filename>.yaml`.
2. `version` matches the PyPI package version — quick-check enforces via `pip install <package>==<version>`.
3. YAML round-trip integrity: `id`, `package`, `version` must survive load/dump
   unchanged. Guards against anchor/alias injection.
4. `dev_install_url`, when present, must be a `git+https://` URL with a host in the
   allowlist: `github.com`, `gitlab.com`.
5. Package name must match PyPI's normalized naming convention.

## Contracts for submitters

- Produce `cube-registry-entry.yaml` via `cube registry add` (cube-standard CLI).
  It reads `pyproject.toml` to pre-fill most fields.
- Leave CI-derived fields empty. Quick-check writes them into the YAML in the PR
  branch before `ready-for-review` is labeled.
- Update by opening a PR that modifies the YAML. Quick-check verifies the submitter
  is listed in `OWNERS.yaml` for that entry.

## Gotchas

- Tags are an open enum — new tags may land via PRs, but canonicalize with an
  existing tag when possible.
- `dev_install_url` lets you register pre-PyPI packages, but pypi publication is
  expected before promotion to `active` status in the site.
- `stress_results/` entries are authored by CI only — humans never write here
  (enforced by path-restricted CI bot).
