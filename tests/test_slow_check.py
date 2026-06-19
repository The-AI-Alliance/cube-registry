"""Tests for scripts/slow_check.py — guards the sandbox debug driver against
drifting from the cube-standard contract again."""

from __future__ import annotations

import ast

from slow_check import DEBUG_SCRIPT


def test_debug_script_is_valid_python():
    ast.parse(DEBUG_SCRIPT)


def test_debug_script_uses_canonical_harness():
    # Must drive the cube via cube.testing.run_debug_suite (which owns the
    # BenchmarkConfig.install()/make() lifecycle) rather than a bespoke loop.
    assert "run_debug_suite" in DEBUG_SCRIPT
    assert "from cube.testing import" in DEBUG_SCRIPT


def test_debug_script_avoids_stale_api():
    # Regression guard: the old driver used a gym-style API that no current cube
    # implements. None of these patterns should reappear.
    # setup() is on the live Benchmark, not the config:
    assert "benchmark.setup()" not in DEBUG_SCRIPT
    # agents are called as agent(obs, action_set), not agent.act(obs):
    assert ".act(" not in DEBUG_SCRIPT
    # task.step returns EnvironmentOutput, not a 4-tuple:
    assert "obs, reward, done" not in DEBUG_SCRIPT


def test_debug_script_takes_package_arg():
    # The package name reaches the sandbox as a CLI arg (--package), never
    # interpolated into the script body — the injection-safety invariant.
    assert "--package" in DEBUG_SCRIPT
    assert 'parser.add_argument("--package"' in DEBUG_SCRIPT
