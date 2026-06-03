# CUBE Registry

The official catalog of CUBE-compliant benchmarks.

[**Browse benchmarks →**](https://the-ai-alliance.github.io/cube-registry)

---

## What is this?

The CUBE Registry is a community-maintained index of benchmarks that implement the
[CUBE standard](https://github.com/The-AI-Alliance/cube-standard). Any CUBE-compliant
evaluation platform or training harness can discover and run registered benchmarks without
custom integration.

Each benchmark is a single YAML file in `entries/`. The registry does not host benchmark
code or data — it points to PyPI packages that do.

---

## Submitting a benchmark

### Prerequisites

Your benchmark package must:
- Be published on PyPI
- Implement the CUBE `Benchmark` and `Task` interfaces
- Expose at least one debug task via `cube/debug_tasks`

**Ready to wrap a benchmark into a CUBE?** See the [Authoring a CUBE guide](https://the-ai-alliance.github.io/cube-standard/authoring-a-cube). The easiest path is the `/new-cube` skill for coding agents, which interviews you, scaffolds the package, fills TODOs, validates, and produces a registry entry end-to-end:

```
/new-cube
```

**Before submitting, self-audit with `/review-cube ./path/to/cube`** — it installs your package, runs pytest + `cube test`, audits against cube-standard invariants, and reports blocking issues locally so you can fix them before CI does.

### Submission steps

**Automated (recommended):** from your cube package directory, run:

```sh
cube registry add --submit
```

This generates the entry YAML from your `pyproject.toml`, forks this repo, commits the entry, and opens a PR via the `gh` CLI. Run `cube registry add` without `--submit` first if you want to edit the YAML locally before opening the PR.

**Manual:**

1. Fork this repository
2. Create `entries/<your-benchmark-id>.yaml` (see template below)
3. Open a pull request

Either way, CI validates the entry. On all checks green, the PR is labeled
`ready-for-review` and a maintainer one-clicks merge — typically within a
business day. Auto-merge for entries is on the roadmap; see
[openspec/changes/entry-auto-merge/](openspec/changes/entry-auto-merge/proposal.md)
for the design.

### Entry template

```yaml
id: your-benchmark-id          # must match filename, globally unique
name: Your Benchmark Name
version: "1.0.0"               # must match PyPI version exactly
description: >
  One paragraph describing what your benchmark tests and why it matters.
package: your-pypi-package-name

authors:
  - github: your-github-handle
    name: Your Name

legal:
  wrapper_license: MIT          # license of this cube wrapper code
  benchmark_license:
    reported: "CC-BY-4.0"      # SPDX identifier, as you understand it
    source_url: "https://github.com/you/benchmark/blob/main/LICENSE"
  notices: []                   # see spec for notice types

paper: "https://arxiv.org/abs/..."   # optional
tags: [web, coding, os, gui, mobile, science, math, multi-agent]
getting_started_url: "https://..."

supported_infra: [aws]          # providers to run compliance checks on
max_concurrent_tasks: 1
parallelization_mode: sequential  # sequential | task-parallel | benchmark-parallel
```

Fields populated automatically by CI (do not fill):
`status`, `resources`, `task_count`, `has_debug_task`, `has_debug_agent`,
`action_space`, `features`, `stress_results_url`

### Updating your entry

Open a PR modifying your existing YAML. CI verifies you are a registered author
(via `OWNERS.yaml`). On checks green, the PR is labeled `ready-for-review` for
a maintainer to merge.

---

## Compliance checks

Every submission goes through two tiers:

| Tier | When | What | Cost |
|---|---|---|---|
| Quick check | On PR (~2 min) | Schema, PyPI install, API introspection | Free |
| Slow check | Post-merge (async) | Full debug episode on real infra | ~$0.05/VM cube |

A slow check failure opens a GitHub issue tagging the entry authors.
Entries remain in the registry regardless — platforms decide which tier they require.

---

## Submitting a result

The registry also hosts a per-cube **community results journal** — one JSON file
per evaluation run, browsable on each cube's page. Submissions are
self-reported; scores are not independently verified.

### Submission format

One file per run at `results/<cube-id>/<sanitized-evaluation-id>.json`,
conforming to [`results-schema.json`](results-schema.json). The file captures
*what was evaluated* (benchmark + version + subset + `n_tasks` denominator) and
*what happened* (aggregate score + std err + mutually-exclusive outcome counts:
success / clean failure / max-steps / system error / missing). No per-task
data — keep raw trajectories on your own infra.

### How to submit

The easiest path is from cube-harness:

```sh
uv run scripts/submit_to_journal.py <experiment_dir>
```

…which builds the JSON, clones cube-registry, and opens a PR via `gh`.

Or manually:

1. Fork cube-registry.
2. Create `results/<cube-id>/<your-evaluation-id>.json` (slashes in the
   evaluation-id are replaced with `__` in the filename).
3. Open a PR. CI validates schema + cross-references the registry + checks
   outcome consistency. If everything passes and the PR strictly adds files
   under `results/`, the PR **auto-merges**.

> ⚠ **Fork PRs auto-merge only when push permissions exist.** GitHub's
> default `GITHUB_TOKEN` is read-only for `pull_request` workflows triggered
> from a fork, so the `gh pr merge --auto` step is a no-op there. Validation
> still runs and posts a green summary — a maintainer will need to complete
> the merge by hand. To get true auto-merge, submit from a branch of this
> repo (`cube registry add` and the cube-harness submitter both support
> this) or wait for the maintainer review.

The journal is **append-only**. Corrections are made by submitting a new
record with a `supersedes` field referencing the prior `evaluation_id`.

---

## Legal

License information in this registry is **self-reported by cube developers** and has not been
verified by the AI Alliance. Always consult the `benchmark_license.source_url` and the
original benchmark authors for authoritative terms.

By submitting an entry, contributors attest that license information is accurate to the best
of their knowledge. See [CONTRIBUTOR_AGREEMENT.md](CONTRIBUTOR_AGREEMENT.md) for full terms.

---

## Specification

Full registry design: [cube-standard/design/registry_specs.md](https://github.com/The-AI-Alliance/cube-standard/blob/design/registry-specs/design/registry_specs.md)
