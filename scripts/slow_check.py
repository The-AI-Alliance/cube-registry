#!/usr/bin/env python3
"""
slow_check.py — CUBE Registry slow compliance check (Tier 2).

Runs a full debug episode against real infra (VM or Docker) for a given provider.
This script is the thin orchestrator that:
  1. Reads the registry entry YAML
  2. Provisions infra from benchmark.resources using the appropriate InfraConfig
  3. Runs a full debug episode (spawn → debug agent → evaluation → close)
  4. Captures stress-test profiling metrics
  5. Writes results to stress-results/<id>/v<version>.json
  6. Updates stress_results_url in the entry YAML

Security model:
- Benchmark code (pip install + Python execution) ALWAYS runs inside a Docker
  container with no cloud credentials forwarded — even for Docker-native benchmarks.
- For VM-based resources, the benchmark package additionally runs INSIDE the
  provisioned VM; this runner only calls the cloud SDK to provision/deprovision.
- Cloud credentials are passed only to the provisioning steps, never to any step
  that touches benchmark code.

Exit codes:
  0 — slow check passed, results written
  1 — slow check failed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Strict allowlist for package names (PyPI normalised naming).
# Prevents code injection when the package name is used in subprocess calls.
_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ENTRIES_DIR = REPO_ROOT / "entries"
STRESS_RESULTS_DIR = REPO_ROOT / "stress-results"

# Debug episode driver, executed inside the hardened sandbox (no credentials).
# It delegates to ``cube.testing.run_debug_suite`` — the SAME harness that
# ``cube test`` runs — so this check can never drift from the cube-standard
# contract. (The previous hand-rolled driver assumed a stale gym-style API:
# ``BenchmarkConfig.setup()`` [setup() is on the live Benchmark, reached via
# ``config.install()`` + ``config.make(infra)``], ``agent.act(obs)`` instead of
# ``agent(obs, action_set)``, and a 4-tuple ``task.step`` return instead of an
# ``EnvironmentOutput`` — so it failed for every compliant cube.)
# The package name is passed as a CLI arg, never interpolated into the body.
DEBUG_SCRIPT = """\
import argparse, importlib, json, sys

parser = argparse.ArgumentParser()
parser.add_argument("--package", required=True)
args = parser.parse_args()

module = importlib.import_module(args.package.replace("-", "_"))

# cube-standard is a dependency of every cube, so its test harness is importable
# here. run_debug_suite resolves get_debug_benchmark() -> BenchmarkConfig, runs
# config.install() + config.make(infra) + episodes + benchmark.close(), and
# returns one report dict per debug task.
from cube.testing import build_stress_test_report, run_debug_suite

results = run_debug_suite(args.package, module, print_json=False)
if not results:
    print("ERROR: no debug episodes ran (empty get_task_configs()?)", file=sys.stderr)
    sys.exit(1)

# On this infra a debug episode must complete and reward 1.0 — same bar as
# `cube test` / assert_debug_tasks_reward_one.
failures = [r for r in results if r.get("error") or not r.get("done") or r.get("reward") != 1.0]

report = build_stress_test_report(args.package, results, compliance_passed=[], compliance_failed=[])
metrics = dict(report.performance)
metrics.update(
    {
        "n_tasks": len(results),
        "mean_reward": round(sum(r.get("reward", 0.0) for r in results) / len(results), 4),
        "all_tasks_passed": not failures,
    }
)
print(json.dumps(metrics))  # parsed by the runner (last JSON line)

if failures:
    summary = [
        {
            "task_id": r.get("task_id"),
            "done": r.get("done"),
            "reward": r.get("reward"),
            "error": r.get("error"),
        }
        for r in failures
    ]
    print("ERROR: debug suite did not pass on this infra: " + json.dumps(summary), file=sys.stderr)
    sys.exit(1)
"""


def load_entry(entry_path: Path) -> dict:
    yaml = YAML()
    with open(entry_path) as f:
        return yaml.load(f)


# ── Isolated Docker-in-Docker (for docker-native cubes) ────────────────────────
_DIND_NET = "cube-slowcheck-net"
_DIND_NAME = "cube-slowcheck-dind"
_DIND_IMG = "docker:27-dind"
_DOCKER_CLI_VERSION = "27.5.1"

# Sandbox base images. Offline/docker cubes use plain slim; browser cubes use the
# official Playwright image, whose system libs (the t64-era chromium deps that
# `playwright install --with-deps` can't resolve on Debian) are prebaked. py3.12
# (noble) matches our pipeline; the image's bundled playwright version is irrelevant
# — `playwright install chromium` re-fetches to match whatever the cube pins.
# MAINTENANCE: pinned for reproducibility; the image only supplies system libs (which
# age slowly), so a stale tag is low-risk, but bump it on a periodic cadence so the
# prebaked libs don't fall behind a cube's newer chromium. Keep the noble-py3.12 line.
_SLIM_IMG = "python:3.12-slim"
_BROWSER_IMG = "mcr.microsoft.com/playwright/python:v1.49.1-noble"


def _start_dind() -> None:
    """Start an isolated Docker-in-Docker daemon on a private network.

    The cube's per-task containers run inside this throwaway, secret-less daemon —
    never on the host (no host docker.sock is ever mounted). ``--privileged`` is
    confined to this disposable nested daemon. Idempotent (clears any prior leak
    before creating) and self-cleaning on failure, so a partial start never
    leaves an orphaned privileged container or network behind.
    """
    _teardown_dind()  # idempotent: clear any leftover container/network first
    try:
        subprocess.run(["docker", "network", "create", _DIND_NET], check=True, capture_output=True)
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--privileged",
                "--name",
                _DIND_NAME,
                "--network",
                _DIND_NET,
                "--network-alias",
                "dind",
                "-e",
                "DOCKER_TLS_CERTDIR=",  # plain TCP within the private network
                _DIND_IMG,
                "dockerd",
                "--host=tcp://0.0.0.0:2375",
            ],
            check=True,
            capture_output=True,
        )
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", _DIND_NAME, "docker", "-H", "tcp://localhost:2375", "info"],
                capture_output=True,
            )
            if ready.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("DinD daemon did not become ready within 60s")
    except Exception:
        _teardown_dind()  # never leave a half-started privileged daemon behind
        raise


def _teardown_dind() -> None:
    subprocess.run(["docker", "rm", "-f", _DIND_NAME], capture_output=True)
    subprocess.run(["docker", "network", "rm", _DIND_NET], capture_output=True)


def resolve_infra_class(entry: dict) -> str:
    """offline | docker | browser | vm.

    Prefer the CI-derived ``infra_class`` (set by quick_check). Fall back to
    ``resources`` (VMResourceConfig → vm); otherwise default to ``docker``, the
    safe superset that also runs offline cubes (just with an unused DinD).

    The docker default trades least-privilege for first-run correctness: an entry
    missing ``infra_class`` (a not-yet-revalidated one, or before quick_check's
    write-back lands in the same run) still works if it's docker-native, at the
    cost of spinning the privileged DinD for an offline cube. This is transitional
    — quick_check stamps ``infra_class`` on every (re)validation — so the fallback
    is dead once entries carry the field. Revisit toward least-privilege if this
    check is ever promoted from advisory to a required auto-merge gate.
    """
    ic = entry.get("infra_class")
    if ic in ("offline", "docker", "browser", "vm"):
        return ic
    resources = entry.get("resources", []) or []
    if any(r.get("type") == "VMResourceConfig" for r in resources):
        return "vm"
    return "docker"


def run_docker_debug_episode(
    entry: dict, provider: str, *, use_dind: bool = False, install_browser: bool = False
) -> dict[str, Any]:
    """
    Run the debug suite (``DEBUG_SCRIPT`` → ``run_debug_suite``) in a creds-free sandbox.

    Security: benchmark code (pip install + Python execution) runs inside a throwaway
    sandbox container with NO credentials forwarded.

    ``use_dind=True`` (docker-native cubes): the sandbox additionally gets the
    ``docker`` client binary (so ``LocalInfraConfig.capabilities()`` detects docker) and
    ``DOCKER_HOST`` → an ISOLATED Docker-in-Docker daemon, where the cube launches its
    per-task containers. The host docker.sock is never mounted.

    ``install_browser=True`` (browser cubes, e.g. miniwob): the sandbox base becomes
    ``_BROWSER_IMG`` (system libs prebaked) and ``playwright install chromium`` fetches
    the browser binary after pip install (NOT ``--with-deps`` — its apt step aborts on
    Debian over Ubuntu-only font packages). No DinD, no privilege — the browser runs
    in-process against the cube's bundled HTML. Mutually exclusive with ``use_dind``
    (browser cubes have no per-task containers).
    """
    package = entry["package"]
    version = entry["version"]
    dev_install_url = entry.get("dev_install_url")

    if not _PACKAGE_NAME_RE.match(package):
        raise RuntimeError(
            f"Invalid package name '{package}'. Must match PyPI normalised naming "
            f"(lowercase letters, digits, hyphens, dots, underscores)."
        )

    # pip install target: versioned PyPI release, or dev_install_url if not yet published.
    # dev_install_url is schema-validated to an allowlisted domain (github.com etc.)
    # so it is safe to use directly as a pip argument.
    pip_target = dev_install_url if dev_install_url else f"{package}=={version}"

    # The debug script (module-level ``DEBUG_SCRIPT``) is written to a temp file
    # and mounted read-only into the container.  The package name is passed as a
    # CLI argument — never interpolated into the script body — so a crafted
    # package name cannot inject code.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(DEBUG_SCRIPT)
        tmp_path = tmp.name

    extra_args: list[str] = []
    cli_prep = "true"
    # Runs AFTER `pip install` (playwright ships with the cube's deps): fetch the
    # chromium binary matching the cube's playwright. System libs are already in
    # _BROWSER_IMG, so NO --with-deps (its Debian apt step can't resolve the
    # Ubuntu-only font packages and aborts the whole install).
    base_image = _BROWSER_IMG if install_browser else _SLIM_IMG
    post_install = "playwright install chromium" if install_browser else "true"
    if use_dind:
        _start_dind()
        extra_args = ["--network", _DIND_NET, "-e", "DOCKER_HOST=tcp://dind:2375"]
        # Static docker *client* only (no daemon) so shutil.which("docker") succeeds.
        _cli_url = (
            "https://download.docker.com/linux/static/stable/"
            f"$(uname -m)/docker-{_DOCKER_CLI_VERSION}.tgz"
        )
        cli_prep = (
            "apt-get install -y -qq --no-install-recommends curl && "
            f"curl -fsSL {_cli_url} | tar xz -C /usr/local/bin --strip-components=1 docker/docker"
        )

    try:
        print(
            f"  [docker-sandbox] debug episode for {package} "
            f"(use_dind={use_dind}, browser={install_browser}, no creds) ..."
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                *extra_args,
                "--memory",
                "8g",
                "--cpus",
                "4",
                "--pids-limit",
                "2048",
                "--cap-drop",
                "NET_ADMIN",
                "--cap-drop",
                "SYS_PTRACE",
                "--cap-drop",
                "SYS_ADMIN",
                "--security-opt",
                "no-new-privileges",
                # Script mounted read-only; no other host paths exposed.
                # IMPORTANT: no --env flags — runner credentials are never forwarded.
                "-v",
                f"{tmp_path}:/debug_script.py:ro",
                base_image,
                "bash",
                "-c",
                "set -e && "
                "apt-get update -qq && "
                "apt-get install -y -qq --no-install-recommends git ca-certificates && "
                f"{cli_prep} && "
                f"pip install --quiet '{pip_target}' && "
                f"{post_install} && "
                f"python /debug_script.py --package {package}",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        if use_dind:
            _teardown_dind()

    if result.returncode != 0:
        raise RuntimeError(f"Docker debug episode failed:\n{result.stderr[-2000:]}")

    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    raise RuntimeError(f"No metrics JSON found in output:\n{result.stdout[-2000:]}")


def run_vm_debug_episode(entry: dict, provider: str) -> dict[str, Any]:
    """
    Run a debug episode using VM resources.
    The benchmark package runs INSIDE the provisioned VM, not here.
    This function orchestrates via cloud SDK (provider-specific).

    In a real implementation, this would:
    1. Call cloud SDK to provision a VM from benchmark.resources
    2. Bootstrap the VM with the benchmark package
    3. Run the debug episode remotely
    4. Collect metrics
    5. Terminate and deregister everything

    For now, this is a placeholder that raises NotImplementedError.
    The actual implementation requires cloud SDK integration (boto3, azure-sdk, etc.)
    """
    raise NotImplementedError(
        f"VM-based slow check for provider '{provider}' requires cloud SDK integration. "
        f"See design/registry_specs.md for the full spec. "
        f"This placeholder must be replaced with actual provisioning logic."
    )


def write_stress_results(
    entry: dict,
    provider: str,
    metrics: dict[str, Any],
    passed: bool,
    error: str | None,
) -> Path:
    """Write stress results to stress-results/<id>/v<version>.json and return the path."""
    benchmark_id = entry["id"]
    version = entry["version"]

    results_dir = STRESS_RESULTS_DIR / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)

    results_file = results_dir / f"v{version}.json"

    # Load existing results to append provider-specific data
    if results_file.exists():
        with open(results_file) as f:
            all_results = json.load(f)
    else:
        all_results = {
            "id": benchmark_id,
            "version": version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "providers": {},
        }

    all_results["providers"][provider] = {
        "passed": passed,
        "error": error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics if passed else {},
    }

    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)

    return results_file


def update_stress_results_url(entry_path: Path, results_path: Path) -> None:
    """Update stress_results_url in the entry YAML."""
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(entry_path) as f:
        doc = yaml.load(f)

    # Store relative path from repo root
    rel_path = results_path.relative_to(REPO_ROOT)
    doc["stress_results_url"] = str(rel_path)

    with open(entry_path, "w") as f:
        yaml.dump(doc, f)


def needs_slow_check(entry_path: Path) -> bool:
    """
    Check if slow check should re-run by comparing changed fields against previous commit.
    Re-runs on: version, package, resources (image_url changes), supported_infra.
    Does NOT re-run for: tags, description, paper, getting_started_url, legal, authors.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD", "--", str(entry_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        diff = result.stdout
        trigger_fields = ["version:", "package:", "image_url:", "supported_infra:", "infra_class:"]
        return any(field in diff for field in trigger_fields)
    except subprocess.CalledProcessError:
        # On error (e.g. first commit), always run
        return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CUBE Registry slow compliance check. Runs a full debug episode on real infra."
    )
    parser.add_argument(
        "--entry",
        required=True,
        metavar="PATH",
        help="Path to the registry entry YAML file.",
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=["aws", "azure", "gcp", "local", "docker"],
        help="Infrastructure provider to test on.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if no trigger fields changed.",
    )
    args = parser.parse_args()

    entry_path = Path(args.entry).resolve()

    print("=== CUBE Registry Slow Check ===")
    print(f"Entry: {entry_path}")
    print(f"Provider: {args.provider}")
    print()

    if not entry_path.exists():
        print(f"::error::Entry file not found: {entry_path}")
        sys.exit(1)

    entry = load_entry(entry_path)
    benchmark_id = entry["id"]

    # Check if slow check needs to run
    if not args.force and not needs_slow_check(entry_path):
        print("ℹ️  No trigger fields changed. Skipping slow check.")
        print("  (Pass --force to override)")
        sys.exit(0)

    infra_class = resolve_infra_class(entry)
    print(f"Infra class: {infra_class}")

    # Run the appropriate check
    passed = False
    error: str | None = None
    metrics: dict[str, Any] = {}

    try:
        if infra_class == "vm" and args.provider not in ("docker", "local"):
            print(f"Running VM-based debug episode on {args.provider}...")
            metrics = run_vm_debug_episode(entry, args.provider)
        else:
            # offline → plain sandbox; browser → sandbox + playwright; docker (or
            # vm at PR-time/local, the safe default) → isolated DinD.
            print(f"Running debug episode (infra_class={infra_class})...")
            metrics = run_docker_debug_episode(
                entry,
                args.provider,
                use_dind=(infra_class not in ("offline", "browser")),
                install_browser=(infra_class == "browser"),
            )

        passed = True
        print(f"\nMetrics: {json.dumps(metrics, indent=2)}")

    except NotImplementedError as e:
        error = str(e)
        print(f"::warning::{e}")
        print("⚠️  VM slow check not yet implemented for this provider.")
        # Don't fail — this is a placeholder
        sys.exit(0)

    except Exception as e:
        error = str(e)
        print(f"::error::Slow check failed for '{benchmark_id}' on {args.provider}: {e}")
        print(f"❌ Slow check FAILED: {e}")

    # Write stress results
    results_path = write_stress_results(entry, args.provider, metrics, passed, error)
    print(f"\nResults written to: {results_path}")

    # Update entry YAML with stress_results_url
    if passed:
        update_stress_results_url(entry_path, results_path)
        print(f"Updated stress_results_url in {entry_path}")
        print("\n✅ Slow check PASSED.")
        sys.exit(0)
    else:
        print("\n❌ Slow check FAILED. Authors will be notified via GitHub issue.")
        sys.exit(1)


if __name__ == "__main__":
    main()
