# Deltas — Nightly monitoring matrix

Changes against [openspec/specs/ci/spec.md](../../specs/ci/spec.md).

---

## ADDED — Nightly monitoring workflow

**New section** to be inserted after "Periodic health check (weekly)":

### Nightly monitoring matrix

Cron-triggered nightly. Runs `cube test <name>` (debug agent, scripted, no LLM) for
every entry in the registry, across each infra target in that entry's
`supported_infra` list.

#### Matrix generation

While `BenchmarkMetadata.CIConfig` is not yet available in cube-standard, the matrix
is derived from:
1. All `entries/<id>.yaml` files where `status != degraded` and `supported_infra` is
   non-empty.
2. Each element of `supported_infra` becomes a column in the matrix.

Once cube-standard gains `CIConfig`, the matrix is generated via
`cube test --list --tier=2` (nightly) and `--tier=1` (PR-level).

#### Per-cell execution

For each (cube, infra) cell:
1. Provision the infra target (same provisioning path as slow-check).
2. Run `cube test <id>` (debug agent); capture exit code, stdout/stderr.
3. On failure: retry up to `retry_count` times (default 2). Record per-attempt result.
4. Write result record to journal.

The runner **never imports the benchmark package** — execution is inside the
provisioned VM/container (same security boundary as slow-check).

#### Statistics per cell

- `pass` / `fail` / `pass_on_retry_N`
- `l1_seconds` — dependency install wall time
- `l2_seconds` — benchmark setup wall time
- `l3_seconds` — per-task reset latency (median over tasks)
- `episode_seconds` — total episode wall time

#### Auto-retry

Default: 2 retries. A future `ci.retry_count` field in cube-standard can override.
Result is `pass` only if the first attempt passes. `pass_on_retry_N` indicates
flakiness. `fail` means all N+1 attempts failed.

---

## ADDED — Journal

**New section** after "Nightly monitoring matrix":

### Journal

Results are appended to `nightly-results/<cube-id>/<infra>/<YYYY-MM-DD>.json`.
Schema per record:

```json
{
  "cube_id": "miniwob-cube",
  "infra": "gh-runner",
  "version": "0.3.1",
  "date": "2026-04-23",
  "attempt": 1,
  "result": "pass",
  "l1_seconds": 14.2,
  "l2_seconds": 3.1,
  "l3_seconds": 0.8,
  "episode_seconds": 47.3,
  "log_url": "https://github.com/.../runs/12345"
}
```

`nightly-results/` is writable only by the CI bot (same path restriction as
`stress-results/`). Humans cannot push to it directly.

---

## ADDED — Dashboard page

**New section** after "generate-site (post-merge)":

### generate-nightly-dashboard (post-nightly)

Runs after the nightly monitoring workflow completes. Reads all journal records and
writes:
- `docs/nightly.html` — the full cube × infra matrix with pass/fail/retry status
- Updates `docs/<cube-id>.html` to show "Latest nightly run: ✓ / ✗" per infra target

Cell color coding:
- Green: latest attempt passed
- Yellow: passed on retry (flaky)
- Red: all attempts failed
- Grey: infra not supported / secret not configured

Each cell links to the GitHub Actions log for that run.

---

## MODIFIED — Invariants

**Append** to existing Invariants list:

6. `nightly-results/` is writable only by the CI bot.
7. Nightly monitoring runs only the debug agent — no LLM API keys are used or
   stored in cube-registry secrets.
8. Cells where required secrets are absent are skipped (recorded as `skipped`), not
   failed.

---

## MODIFIED — Workflow list

**In the "Pipeline overview" section**, update the file list:

```
.github/workflows/{quick-check,slow-check,update-owners,generate-site,
                   periodic-health-check,manual-refresh,nightly-monitoring}.yml
```

**Add to pipeline diagram:**

```
nightly cron
 └─ nightly-monitoring  (cube test for all entries × infra, ~varies)
     └─ generate-nightly-dashboard  (updates docs/nightly.html)
```

---

## NOT CHANGED

- Ownership check (every PR) — unchanged
- Quick compliance (every PR) — unchanged
- Slow compliance (post-merge) — unchanged
- Periodic health check (weekly) — unchanged
- Manual refresh — unchanged
- Security boundaries for `OWNERS.yaml`, `stress-results/`, `docs/` — unchanged
