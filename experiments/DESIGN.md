# Slow-check debug-agent execution — validated design

## Goal
Actually run the debug agents on the debug tasks (assert `reward==1.0`) for cubes
that need **Docker or less**, safely, in CI — replacing the hand-rolled debug
script that (a) doesn't match the real debug API and (b) can't launch per-task
containers.

## The gap (today)
`slow_check.run_docker_debug_episode` pip-installs the cube into a creds-free
`python:3.12-slim` sandbox and runs a *reimplemented* debug episode. That works
for offline cubes but: the reimplementation calls `make()` without
`runtime_context`, uses a wrong agent/step API, and — fatally — the sandbox has
**no Docker**, so a Docker-native cube (swegym/swebench) can't even `reset()` a
task. It also mis-detects infra class from `benchmark.resources` (empty for
per-task-container cubes).

## The design (validated locally — see RESULTS)
One self-contained runner, security-preserving, keyed by **infra class**:

```
host docker (GitHub x86 runner / colima)
├── dind            privileged, ISOLATED, tcp://dind:2375 on a private net   ← docker-mode only
└── sandbox         creds-free (no --env), no host socket, capped
      └── DEBUG_SCRIPT → cube.testing.run_debug_suite   (the canonical harness
            │                                            that `cube test` also wraps)
            └── launches per-task containers INSIDE dind
```

> Implementation note: the runner invokes `run_debug_suite` directly via the existing
> `DEBUG_SCRIPT` (mounted into the sandbox), not the `cube test` CLI — both drive the
> identical harness (`install()` → `make(infra)` → episodes, asserts reward==1.0) and
> `run_debug_suite` additionally yields the per-task report `build_stress_test_report`
> consumes for metrics. The local prototypes (`debug_run.sh`) used the `cube test` CLI;
> they are equivalent.

- **offline** cubes → plain creds-free sandbox; `cube test <id>` runs in-process. No DinD, no privilege.
- **docker** cubes → same sandbox + an **isolated Docker-in-Docker** sidecar; sandbox gets the
  `docker` **client binary** (so `LocalInfraConfig.capabilities()` = `shutil.which("docker")`
  detects docker) + `DOCKER_HOST=tcp://dind:2375`. The cube launches its task containers inside
  DinD. No host docker.sock, no host credentials.
- **browser** cubes (e.g. miniwob) → in-process browser against the cube's bundled HTML, no
  per-task containers. Sandbox base = the official **Playwright noble image** (py3.12, chromium
  system libs prebaked) + `playwright install chromium` after pip install. No DinD, no privilege.
  (`--with-deps` is avoided: on Debian-slim its apt step lists Ubuntu-only font packages with no
  candidate and aborts; the Playwright image already carries the libs.)
- **vm** cubes → unchanged stub (post-merge, separate phase).

> **Beyond these four:** webarena-verified / workarena are *browser + external services* (live
> mirror sites, a ServiceNow SaaS instance) — un-sandboxable in a creds-free runner, same bucket
> as the VM cubes. They are out of scope for the local/docker slow-check.

### Why it's safe
- Benchmark code never sees credentials (no `--env` into the sandbox).
- The cube's task containers run inside the **isolated DinD**, never on the host daemon
  (no `-v /var/run/docker.sock`). DinD is throwaway, capped, on an ephemeral runner.
- The only added privilege is the DinD sidecar (`--privileged`) — a nested, secret-less,
  disposable daemon. Standard pattern for untrusted container workloads in CI.

### Infra-class detection (in quick_check, which already imports the cube)
`vm` if any benchmark-level `VMResourceConfig`; else `docker` if any
`task_metadata[*].container_config` is set; else `browser` if `playwright` is
importable (a browser-tool dep); else `offline`. Short-circuits cheaply.
Emitted as a CI-derived field the runner reads.

## RESULTS (local, colima arm64 + Rosetta)
- creds-free sandbox drove an isolated nested DinD and launched a container: `HELLO_FROM_DIND` ✓
- amd64 runs inside nested DinD (`uname -m` → x86_64 via shared Rosetta) ✓
- offline `cube test counter-cube`: **7/7 compliance, 3 tasks reward 1.0** ✓
- docker `cube test swegym-cube` via isolated DinD: **7/7 compliance, getmoto+dvc reward 1.0**,
  amd64 task containers, no host creds/socket ✓

GitHub-hosted runners are x86_64 → SWE-bench `amd64` images run **natively** (no emulation),
so CI is faster than this local proof.

## Rollout
Keep `slow-compliance` `continue-on-error` (advisory) until green across existing Docker cubes,
then promote to a required check for the trusted-author auto-merge tier.

## Follow-ups
- `cube test --json` in cube-standard for clean metric capture (vs. exit-code-only / panel parse).
- Disk: set DinD data-root on the runner's large mount; prune between tasks. Wall-clock timeout.
- Egress allowlist during eval (defense-in-depth) — Phase 4.
