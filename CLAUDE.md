# CLAUDE.md — cube-registry

You are working in **cube-registry**, the public catalog of CUBE-compliant
benchmarks. This is a metadata-only repo — it hosts YAML entries and CI scripts,
not benchmark code.

## What this repo is

One YAML file per benchmark in `entries/`, a JSON Schema to validate them, CI to
enforce ownership and compliance, and a Jinja2-based static site. Benchmarks
themselves live on PyPI; entries only reference them.

## Package layout

```
cube-registry/
├── entries/                       One YAML per benchmark (globally unique id)
├── OWNERS.yaml                    id → [github handles]; written only by CI bot
├── known-authors.yaml             Manually curated: original paper authors
├── registry-schema.json           JSON Schema for entry validation
├── stress-results/                Written by slow-check only
├── scripts/                       CI pipeline scripts
│   ├── ownership_check.py
│   ├── quick_check.py
│   ├── slow_check.py
│   ├── health_check.py
│   └── update_owners.py
├── site-src/                      Jinja2-based site generator → docs/
│   ├── generate.py
│   └── templates/
├── docs/                          Generated output — NEVER edit by hand
├── .github/workflows/
│   ├── quick-check.yml
│   ├── slow-check.yml
│   ├── update-owners.yml
│   ├── generate-site.yml
│   ├── periodic-health-check.yml
│   └── manual-refresh.yml
├── tests/                         pytest for scripts/ and site-src/
└── openspec/specs/                Authoritative specs for entry / CI / site
```

## Spec index

| Capability | Spec |
|------------|------|
| YAML entry schema (author-provided vs CI-derived fields) | [entry/spec.md](openspec/specs/entry/spec.md) |
| CI pipeline (ownership, quick, slow, health) | [ci/spec.md](openspec/specs/ci/spec.md) |
| Static site generation | [site/spec.md](openspec/specs/site/spec.md) |

## Workflow for code changes

1. **Schema changes** (adding/removing fields) → update `registry-schema.json`, the
   entry spec, and at least one example entry. Consider migration for existing entries.
2. **CI logic** (scripts/) → every change must preserve security boundaries (see
   [ci/spec.md](openspec/specs/ci/spec.md) Invariants).
3. **Site templates** → regenerate `docs/` via CI. Never commit `docs/` changes by
   hand — CI's `generate-site.yml` is the source of truth.
4. **OpenSpec changes**: for anything non-trivial, create
   `openspec/changes/<name>/{proposal.md,deltas.md}` before coding.

## Security boundaries (do NOT violate)

- `OWNERS.yaml` is writable only by the CI bot (path-restricted bypass rule).
- `stress-results/` is writable only by the CI bot.
- `docs/` is writable only by the CI bot (via `generate-site`).
- Ownership check reads `origin/main`, never the PR branch.
- Quick-check runs in a hardened Docker sandbox WITHOUT cloud credentials.
- Slow-check has credentials but NEVER imports the benchmark package — the package
  executes inside the provisioned VM.
- GitHub handles are validated against `^[a-zA-Z0-9][a-zA-Z0-9-]{0,37}$`.
- Package names are validated against PyPI normalization before passing to `pip`.
- YAML round-trip integrity check on `id`, `package`, `version` to guard against
  anchor/alias injection.

Any change that would relax one of these boundaries MUST go through an openspec
change proposal with explicit threat-model review.

## Development

```bash
uv sync --all-extras
uv run pytest tests/ -v
uv run python site-src/generate.py --entries entries/ --output docs/
```

## What lives elsewhere

- **cube-standard** — the protocol benchmarks implement; `cube registry add` (CLI)
  scaffolds a registry entry from a `pyproject.toml`.
- **cube-harness** — runs experiments against these benchmarks.
- Benchmark code — individual packages on PyPI, one per `entries/<id>.yaml`.
