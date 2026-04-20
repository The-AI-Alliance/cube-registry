# Static Site Generation

**Module:** `site-src/generate.py`
**Output:** `docs/` (served by GitHub Pages — zero hosting cost)

## Purpose

Render the registry as a browseable static site. Reads `entries/*.yaml` + latest
`stress-results/*.json` and produces HTML via Jinja2 templates. Deployed to
`https://the-ai-alliance.github.io/cube-registry`.

## Outputs

```
docs/
├── index.html                     # card grid with filters (tags, status, infra)
├── <id>/index.html                # one per entry: full metadata
├── assets/                        # CSS, JS, images
└── .nojekyll                      # tells GH Pages to serve docs/ as-is
```

### Index page

Card grid with search and filter. Each card:
- Benchmark name + status badge (`active` | `degraded` | `archived`)
- One-line description
- Tags
- Task count
- Copy button: `pip install <package>==<version>`

### Per-benchmark page

- Full metadata (description, authors, paper link, version)
- Resources table (from CI-derived `resources` field)
- Feature flags (`async`, `streaming`, `multi_agent`, `multi_dim_reward`)
- Legal section (licenses, notices)
- Latest stress results (if available)
- Copy-to-clipboard install command

## Invariants

1. `docs/` is always a CI-generated artifact. Never edit by hand — every manual
   edit is overwritten on the next merge.
2. The generator is deterministic: same inputs → same outputs. CI commits only when
   content actually changes (via git diff check).
3. Unreachable `legal.benchmark_license.source_url` entries don't break the build —
   they surface as warnings, and the card's license chip links out anyway.
4. Stress results that reference a non-existent entry are ignored (orphans).

## Gotchas

- Mermaid diagrams and custom CSS require `_includes/` templates — the generator
  copies these into the output tree.
- `.nojekyll` MUST be present in `docs/` — without it, GitHub Pages tries to run
  Jekyll over the generated HTML and mangles underscored assets.
- The index page grows unbounded as entries accumulate. Client-side filtering is
  lunr.js-based; revisit pagination if entry count exceeds a few hundred.
