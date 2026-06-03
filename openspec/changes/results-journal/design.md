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
  dependency_versions, primary_dependencies?, git_commit, git_remote_url,
  git_is_dirty, cube_standard_git_commit, cube_standard_git_is_dirty,
  config?}`. Matches cube-harness's `AgentInfo` 1-to-1.
  - `dependency_versions` is the sys.modules-filtered + drop-list-pruned
    set of installed distribution versions at run time (~45 packages on a
    typical recipe, down from ~200 in a full pip freeze).
  - `primary_dependencies` is an optional `list[str]` flagging the subset
    whose drift most directly affects scores (LLM gateway + provider SDKs,
    tokenizers, env runtimes, HTTP/retry stack). Downstream UIs render
    these prominently; the rest live in `dependency_versions`.
  - `config?` is the full serialized agent config (optional, included when
    submitter opts in for reproducibility).
  - All free-text string fields are bounded by `maxLength` caps (typically
    128–256) so a malicious submitter can't fit a large payload through.
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

## Sample record (hashes truncated for readability)

> A real submission has 64-hex `agent_id`, 40-hex `git_commit`s, and full
> dependency-version lists. The ellipses below would fail the JSON-schema
> patterns — they're shown short purely so a reviewer can scan the shape.

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
    "dependency_versions": {
      "cube-harness": "0.5.2", "cube-standard": "0.3.1", "litellm": "1.55.0",
      "openai": "1.50.0", "playwright": "1.40.0", "httpx": "0.27.0",
      "tiktoken": "0.7.0", "tokenizers": "0.15.2", "pydantic": "2.7.0",
      "numpy": "1.26.4", "jsonschema": "4.21.1"
    },
    "primary_dependencies": [
      "cube-harness", "cube-standard", "litellm", "openai", "playwright",
      "tiktoken", "tokenizers", "pydantic"
    ],
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

## Validator + workflow decision tree

The path-isolation and append-only enforcement happen in `results-check.yml`,
not in the Python validator. The Python validator runs over a batch of
already-added files and checks per-file invariants + batch-wide dedup.

```yaml
# results-check.yml (simplified)
classify:
  outputs:
    added_results:           tj-actions/changed-files files_yaml: results/*/*.json, ignore _*
    modified_or_deleted_any: git diff --diff-filter=MDRC -- 'results/*'  ≠ ∅
    non_results_any:         (all-changed) ∖ (results/**)  ≠ ∅

reject-modify:               if modified_or_deleted_any:           comment + exit 1
validate:                    if added_results_any and not modified_or_deleted_any:
                                 python scripts/results_check.py
                                   --added "$ADDED_FILES"      # via env, NEVER ${{ }}
auto-merge:                  if all of (added_results_any, not modified_or_deleted_any,
                                       not non_results_any, validate.passed):
                                 gh pr merge --auto --squash
request-human-review:        if added_results_any and not modified_or_deleted_any
                                       and non_results_any and validate.passed:
                                 comment only (no auto-merge)
```

```python
# scripts/results_check.py — per-file check_file(path, schema, sibling_added_ids)
# Numbering matches deltas.md so reviewers can cross-reference. Some deltas
# entries are co-located here ("path-shape + underscore reject" both land in
# _file_to_cube_id; "sibling-batch dedup" + on-disk dedup both fire from the
# evaluation_id uniqueness block).
1.  file size ≤ 50 KB
2.  _file_to_cube_id(path)             # cube-id segment ^[a-z0-9](-[a-z0-9]+)*$,
                                       # filename does NOT start with '_' (delta #12)
3.  json.loads(path)                   # invalid JSON => fail
4.  Draft7Validator(schema).validate   # schema meta-validated at load (delta #1)
5.  cross-ref entries/<cube>.yaml      # cube must be registered (delta #2)
6.  benchmark_name == cube-id          # (delta #3)
7.  benchmark_version ∈ known set      # entry.version + prior file versions (delta #4)
8.  benchmark_subset.n_tasks ≤ entry.task_count                          # (delta #5)
9.  outcomes sum == n_tasks            # mutually exclusive + exhaustive  (delta #6)
10. primary_dependencies ⊆ dependency_versions                            # (delta #9)
11. filename stem == sanitize(evaluation_id)                              # (delta #12)
12. evaluation_id ∉ on_disk_ids AND ∉ sibling_added_ids                  # (delta #11)
                                       # both signals fire independently when overlapping
# (avg_score bounds, git_commit shape, and the maxLength caps are
# delta #7/#8 + the per-field schema caps — enforced by the JSON Schema
# validator above, not by additional Python.)
```

Failure messages are surfaced as a single PR comment for the submitter to act
on, formatted as a checklist.

---

## Merge-time bookkeeping

`results-check.yml` runs on `pull_request`. A separate `record-submitter.yml`
runs on `push` to `main` with path filter `results/*/*.json` (post-merge,
write permissions via the existing path-restricted bypass that already
governs `OWNERS.yaml`/`stress-results/`). It appends one
row to `results/<cube-id>/_submissions.json` mapping `evaluation_id → PR author
GitHub handle + merge timestamp`. The `_submissions.json` file is the
authoritative source for the `Submitter` column in the site table.

`_submissions.json` is writable only by the CI bot (same path-restriction
mechanism as `OWNERS.yaml`).

---

## Site rendering

`site-src/generate.py` gains `load_results(entry)` (newest-first, attaches
`_submitter` from `_submissions.json` and `_detail_url` pointing at the raw
JSON on GitHub) and `_json_for_html_script(data)` which serializes the
records into a script tag with `<` / `>` / `&` escaped as `\uXXXX`:

```python
def _json_for_html_script(data):
    return (json.dumps(data, separators=(",", ":"))
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))

# benchmark.html.j2
<script id="results-data" type="application/json">{{ results_json | safe }}</script>
<script src="https://unpkg.com/gridjs/dist/gridjs.umd.js"></script>
<script>
  const RESULTS = JSON.parse(document.getElementById('results-data').textContent);
  // → Grid.js table with checkbox selection
  // → compare-N modal with diff highlighting
  // → primary/secondary dependency tiering inside the deps cell
</script>
```

Rows are sorted newest-first by `evaluation_timestamp`. Grid.js handles
per-column sort, search, and 20-row pagination. The compare modal is
custom — vanilla DOM, ~150 lines of inline JS.

The Subset cell uses a two-line layout that surfaces the subset shape at a
glance: the `benchmark_subset.name` on top, and one of
`<filter> · N tasks` / `custom: N tasks` / `N tasks` on the bottom
(depending on whether `filter` is set, `task_ids` is set, or neither).
This lets a reader distinguish a full named subset from a hand-picked list
or a debug-truncated run without opening the modal.

---

## Anti-abuse posture

The path-isolation gate + size cap + schema validation cover the realistic
abuse modes. Each item below maps to a specific code-review finding from the
multi-agent review:

- **Spam**: 50 KB cap + per-cube directory means abuse PRs are bounded and
  easy to revert as a batch. Per-field `maxLength` caps (typically 128–256
  on free-text strings; `maxProperties: 500` on `dependency_versions`;
  `maxItems: 50` on `primary_dependencies`; `maxItems: 1000` on
  `task_ids`) tighten the available attack surface.
- **Schema injection**: `additionalProperties: false` everywhere + strict
  types + `Draft7Validator.check_schema()` at validator load (catches
  schema-side typos at CI start).
- **Cross-cube pollution**: filename-path-content cross-checks (cube-id
  from the path, JSON `benchmark_name`, and an existing entry must all
  agree). Underscore-prefixed filenames are reserved for CI-bot
  bookkeeping and rejected at the path-check stage.
- **Modifying others' results**: append-only enforcement via
  `git diff --diff-filter=MDRC` in the classify job — the only way to
  affect an existing record is a `supersedes` reference in a new file.
- **Sibling-batch dedup**: two added files with the same `evaluation_id`
  in one PR both fail. On-disk dedup catches it in the typical CI checkout
  case; the sibling-batch check is defense in depth for local runs.
- **Shell injection through PR-author paths**: env-var passthrough +
  `xargs` invocation; `${{ }}` substitution into a `run:` block is never
  used for PR-author-controlled values.
- **XSS via auto-merged JSON**: `_json_for_html_script` escapes `<` / `>` /
  `&` as `\\uXXXX` so a `</script><script>...` payload in any free-text
  field is rendered inert by the HTML tokenizer (the browser's `JSON.parse`
  decodes the escapes back to the original characters).
- **Faked scores**: not preventable by structural validation — explicit
  non-goal per the proposal.
- **Fork-PR auto-merge limitation**: `GITHUB_TOKEN` is read-only on
  `pull_request` from a fork in public repos, so `gh pr merge --auto` is a
  no-op. Validation still runs and posts a green summary; a maintainer
  completes the merge by hand. Documented in README. The cube-harness
  submitter (`scripts/submit_to_journal.py --auto-pr`) handles fork PRs
  correctly by forking via `gh repo fork --clone` first.

If abuse becomes a real problem post-launch, add a rate-limit
(N-submissions-per-author-per-day) and/or a "verified" tier — both
incrementally addable without redesign.
