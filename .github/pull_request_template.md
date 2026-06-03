## CUBE Registry Submission

Thank you for submitting a benchmark to the CUBE Registry!
CI runs three pre-merge hard gates (ownership, quick-compliance, LLM
semantic review) plus an informational slow-compliance signal. On hard
gates green and a path-isolated diff under `entries/<id>.yaml`, the PR
auto-merges.

---

### Checklist

- [ ] I have read [CONTRIBUTOR_AGREEMENT.md](../CONTRIBUTOR_AGREEMENT.md) and agree to its terms
- [ ] My entry file is named `entries/<id>.yaml` where `<id>` matches the `id` field in the YAML
- [ ] I have **NOT** modified any CI-derived fields (`status`, `resources`, `task_count`, `has_debug_task`, `has_debug_agent`, `action_space`, `features`, `stress_results_url`)
- [ ] I have published my package to PyPI at the version specified in `version`
- [ ] My package exports a `Benchmark` class that implements the CUBE interface
- [ ] My benchmark declares at least one debug task via `cube/debug_tasks`
- [ ] License information in `legal` is accurate to the best of my knowledge

---

### What CI will check

| Check | When | ~Time | Hard gate? |
|---|---|---|---|
| ownership-check | On PR | <1 min | Yes |
| quick-compliance (schema + install + introspect) | On PR | ~2 min | Yes |
| slow-compliance (debug task on runner) | On PR | ~5 min | No (informational) |
| entry-review (LLM semantic check) | On PR | ~1 min | Yes |
| Full stress run on `supported_infra` cloud VMs | Post-merge (async) | ~5-30 min | Post-merge canonical |

When all hard gates pass AND the diff is strictly under
`entries/<id>.yaml` AND the PR is from this repo (not a fork), the PR
auto-merges. Otherwise it's labeled `ready-for-review` for a maintainer
(the comment will list the specific reasons). slow-compliance failing
shows as a red check but does not block — cubes that need Docker/VM/etc.
naturally can't run with `provider=local`.

The post-merge stress run runs asynchronously after merge. A failure opens
a GitHub issue tagging your `authors[].github` handles; the entry stays in
the registry with `status: degraded` until fixed.

---

### Notes

- **CI-derived fields** (`resources`, `task_count`, `features`, etc.) will be **overwritten**
  by CI even if you fill them in. Leave them blank or omit them entirely.
- **OWNERS.yaml** is updated automatically after merge — do not modify it in your PR.
- **stress-results/** is managed exclusively by CI — do not create or modify files there.
- Need help? See the [README](../README.md) or open an issue.
