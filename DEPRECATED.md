# Deprecated — cube-registry

Code and artifacts flagged for future cleanup. Each item is actionable — remove,
replace, rewrite, or consolidate. Nothing here is currently in progress; the list
exists so we can pick up simplification work when timing allows.

---

## Dead / unused

### `known-authors.yaml` — empty template, dead feature dependency
[known-authors.yaml](known-authors.yaml)

File is an empty template. CI populates
`legal.benchmark_license.verified_by_original_authors` in entries based on this
file, but with no data source it's always `false`.

Dependent code to remove alongside:
- `check_verified_by_original_authors()` in [scripts/quick_check.py](scripts/quick_check.py) (~line 332)
- `verified_by_original_authors` field in [registry-schema.json](registry-schema.json) (~line 87-90)

**Action:** either (a) populate with a sourcing policy + data, or (b) remove the
file, the check function, and the schema field in one PR.

### `action_space` schema field — never populated
[registry-schema.json:191-201](registry-schema.json#L191-L201) and
[scripts/quick_check.py:311-327](scripts/quick_check.py#L311-L327)

`quick_check.py` attempts to introspect `action_space` from a reset task but the
logic fails silently — output is `::notice::Could not introspect action_space`
and no entry in [entries/](entries/) has it populated.

**Action:** remove the schema definition and the introspection attempt. If a
consumer ever needs it, implement properly with explicit error handling.

### Obsolete `.gitkeep` files
- [docs/.gitkeep](docs/.gitkeep) — `docs/` has generated content
- [entries/.gitkeep](entries/.gitkeep) — `entries/` has real YAML files
- [stress-results/.gitkeep](stress-results/.gitkeep) — populated on first slow-check run

**Action:** delete all three.

---

## Inconsistencies to fix

### README claims auto-merge; spec says maintainer review
[README.md:43](README.md#L43) and [README.md:82](README.md#L82) say:

> CI will validate your entry and auto-merge if it passes. No human review needed.

But [openspec/specs/ci/spec.md:58](openspec/specs/ci/spec.md#L58) and
[openspec/specs/ci/spec.md:114](openspec/specs/ci/spec.md#L114) say:

> No auto-merge — a human approves before anything lands on main.

**Action:** pick one and update the other. Recommendation: update README to match
spec (safer default; easy to relax later).

### Broken design-doc link in README
[README.md:113](README.md#L113)

Points at `cube-standard/blob/design/registry-specs/design/registry_specs.md`
— a branch that doesn't exist. The content has moved to
[cube-registry/openspec/specs/](openspec/specs/).

**Action:** replace with a link to `openspec/specs/{entry,ci,site}/spec.md` or
remove the Specification section entirely.

---

## Duplication to consolidate

### YAML initialization duplicated across scripts
[scripts/quick_check.py](scripts/quick_check.py),
[scripts/slow_check.py](scripts/slow_check.py),
[scripts/update_owners.py](scripts/update_owners.py),
[scripts/health_check.py](scripts/health_check.py)

Every script creates its own `YAML()` instance with near-identical settings. Drift
risk as settings diverge silently.

**Action:** add `scripts/_yaml.py` with:

```python
from ruamel.yaml import YAML

def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y

def load(path): ...
def dump(data, path): ...
```

Import from every script. Consistent round-trip, single source of truth for YAML
config.
