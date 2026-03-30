## CUBE Registry Submission

Thank you for submitting a benchmark to the CUBE Registry!
CI will validate your entry automatically — no human review needed in the happy path.

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

| Check | When | ~Time |
|---|---|---|
| Schema validation | On PR | <1 min |
| PyPI install + API introspection | On PR | ~2 min |
| Full debug episode on real infra | Post-merge (async) | ~5-15 min |

Auto-merge triggers when `ownership-check` and `quick-compliance` both pass.

The slow check runs asynchronously after merge. A failure will open a GitHub issue tagging
your GitHub handle from `authors[].github`.

---

### Notes

- **CI-derived fields** (`resources`, `task_count`, `features`, etc.) will be **overwritten**
  by CI even if you fill them in. Leave them blank or omit them entirely.
- **OWNERS.yaml** is updated automatically after merge — do not modify it in your PR.
- **stress-results/** is managed exclusively by CI — do not create or modify files there.
- Need help? See the [README](../README.md) or open an issue.
