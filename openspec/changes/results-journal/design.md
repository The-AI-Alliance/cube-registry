# Design — Community results journal

Implementation notes for the validator, schema, and merge-time bookkeeping.

---

## Schema sketch (`results-schema.json`)

Top-level required fields (JSON Schema draft-07):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "evaluation_id", "evaluation_timestamp",
    "eval_library", "agent", "benchmark_name", "benchmark_version",
    "benchmark_subset", "results"
  ],
  "properties": {
    "schema_version":     {"const": "1.0"},
    "evaluation_id":      {"type": "string", "pattern": "^[A-Za-z0-9_./-]{1,128}$"},
    "evaluation_timestamp": {"type": "number"},
    "supersedes":         {"type": "string", "description": "evaluation_id this record corrects"},
    "eval_library":       {"$ref": "#/$defs/eval_library"},
    "agent":              {"$ref": "#/$defs/agent"},
    "benchmark_name":     {"type": "string"},
    "benchmark_version":  {"type": "string"},
    "benchmark_subset":   {"$ref": "#/$defs/benchmark_subset"},
    "results":            {"$ref": "#/$defs/results"},
    "findings_summary":   {"type": "object", "additionalProperties": {"type": "integer"}},
    "instance_results_url": {"type": "string", "format": "uri"}
  }
}
```

`$defs`:

- `eval_library` — `{name, version}` (e.g. `{"name": "cube-harness", "version": "0.5.2"}`)
- `agent` — `{agent_id, config_type, llm_model, framework_version,
  dependency_versions, git_commit, git_remote_url, git_is_dirty,
  cube_standard_git_commit, cube_standard_git_is_dirty, config?}`. Matches
  cube-harness's `AgentInfo` 1-to-1; `config?` is the full serialized agent
  config (optional, included when submitter opts in for reproducibility).
- `benchmark_subset` — `{name, n_tasks, filter?, task_ids?}`. `name` is the
  display label (e.g. `miniwob[level=all]`); `filter` is the derivation
  expression (filter string, glob, or named split); `n_tasks` is the
  denominator; `task_ids` (optional) is the explicit list when neither name
  nor filter uniquely pins the subset.
- `results` — top-level aggregates plus a typed outcomes breakdown:
  `{avg_score, std_err, total_cost_usd, avg_wall_time_s,
    max_steps_per_episode, outcomes}` where `outcomes` is mutually exclusive
  and exhaustive over `benchmark_subset.n_tasks`:
  - `n_success` — episode reached `done=True` with reward > 0
  - `n_failure` — episode reached `done=True` with reward == 0 (clean fail per the verifier)
  - `n_max_steps` — loop exited because the step cap fired before `done=True` (no agent crash)
  - `n_system_error` — episode aborted with an exception (agent crash, infra failure, tool error)
  - `n_missing` — task in the subset but never attempted (e.g. infra unavailable)

  Validator constraint: `n_success + n_failure + n_max_steps + n_system_error + n_missing == benchmark_subset.n_tasks`.

The schema is a near-1:1 flatten of cube-harness's
`ExperimentRecord` + aggregated `EpisodeRecord` stats. No translation layer
needed — the cube-harness submitter calls `model_dump` and reshapes ~12 fields.

---

## Sample valid record

```json
{
  "schema_version": "1.0",
  "evaluation_id": "alacoste/20260404_195953_genny_miniwob",
  "evaluation_timestamp": 1748560000,
  "eval_library": {"name": "cube-harness", "version": "0.5.2"},
  "agent": {
    "agent_id": "a3f9e2d4c1b8...",
    "config_type": "GennyConfig",
    "llm_model": "azure/gpt-5.4-mini",
    "framework_version": "0.5.2",
    "dependency_versions": {"cube-harness": "0.5.2", "cube": "0.3.1", "litellm": "1.55.0"},
    "git_commit": "f6a3b2e9d8c1b4a7...",
    "git_remote_url": "https://github.com/The-AI-Alliance/cube-harness/tree/f6a3b2e...",
    "git_is_dirty": false,
    "cube_standard_git_commit": "8e2b9c4a1d7f3e6b...",
    "cube_standard_git_is_dirty": false
  },
  "benchmark_name": "miniwob",
  "benchmark_version": "1.0.0",
  "benchmark_subset": {"name": "miniwob[level=all]", "n_tasks": 125, "filter": "level=all"},
  "results": {
    "avg_score": 0.664,
    "std_err": 0.043,
    "total_cost_usd": 12.34,
    "avg_wall_time_s": 47.2,
    "max_steps_per_episode": 30,
    "outcomes": {
      "n_success": 83,
      "n_failure": 32,
      "n_max_steps": 7,
      "n_system_error": 3,
      "n_missing": 0
    }
  }
}
```

File path: `results/miniwob/alacoste__20260404_195953_genny_miniwob.json`
(slashes in `evaluation_id` are replaced with `__` for the filename).

---

## Validator decision tree (`scripts/results_check.py`)

```
diff = github.pulls.get_files(pr)
results_added  = [f for f in diff if f.status == "added" and f.path startswith "results/"]
non_results    = [f for f in diff if not f.path startswith "results/"]
results_other  = [f for f in diff if f.status != "added" and f.path startswith "results/"]

if results_other:                  # modify/delete in results/
    fail("results/ is append-only")
if non_results:                    # mixed PR
    inform("mixed PR — falling back to human review"); exit 0

for f in results_added:
    record = json.loads(f.content)
    run_per_file_checks(record, path=f.path)   # see deltas.md, 10 items

if all_passed:
    apply_label("auto-merge")
else:
    post_comment(failures); exit 1
```

Failure messages are surfaced as a single PR comment for the submitter to act
on, formatted as a checklist.

---

## Merge-time bookkeeping

`results-check.yml` runs on `pull_request`. A separate `record-submitter.yml`
runs on `pull_request_target` (post-merge, write permissions) and appends one
row to `results/<cube-id>/_submissions.json` mapping `evaluation_id → PR author
GitHub handle + merge timestamp`. The `_submissions.json` file is the
authoritative source for the `Submitter` column in the site table.

`_submissions.json` is writable only by the CI bot (same path-restriction
mechanism as `OWNERS.yaml`).

---

## Site rendering

`site-src/generate.py` gains:

```python
for cube_id, entry in entries.items():
    results = []
    for fp in (root / "results" / cube_id).glob("*.json"):
        if fp.name.startswith("_"):     # skip _submissions.json
            continue
        results.append(json.loads(fp.read_text()))
    submitters = json.loads((root / "results" / cube_id / "_submissions.json").read_text())
    render("benchmark.html.j2", entry=entry, results=results, submitters=submitters)
```

V1 template renders the table from `deltas.md`. Rows sorted by
`evaluation_timestamp` descending. No JS dependencies; columns are
HTML-sortable via a small inline `<script>` for column-click sort (acceptable
size, no external deps).

---

## Anti-abuse posture

The path-isolation gate + size cap + schema validation cover the realistic
abuse modes:

- **Spam**: 50 KB cap + per-cube directory means abuse PRs are bounded and easy
  to revert as a batch.
- **Schema injection**: `additionalProperties: false` everywhere + strict types.
- **Cross-cube pollution**: filename-path-content cross-checks (the cube id from
  the path, the JSON `benchmark_name`, and an existing entry must all agree).
- **Modifying others' results**: append-only enforcement.
- **Faked scores**: not preventable by structural validation — explicit
  non-goal per the proposal.

If abuse becomes a real problem post-launch, add a rate-limit
(N-submissions-per-author-per-day) and/or a "verified" tier — both
incrementally addable without redesign.
