"""
Shared test fixtures and helpers for cube-registry tests.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

# Ensure repo root is on path so scripts/ can be imported
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "site-src"))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def schema(repo_root) -> dict:
    """Load registry-schema.json."""
    with open(repo_root / "registry-schema.json") as f:
        return json.load(f)


@pytest.fixture
def minimal_entry() -> dict:
    """A minimal valid entry with only required fields."""
    return {
        "id": "my-bench",
        "name": "My Benchmark",
        "version": "1.0.0",
        "description": "A benchmark for testing purposes, covering various tasks.",
        "package": "my-bench-cube",
        "authors": [{"github": "author1"}],
        "legal": {"wrapper_license": "MIT"},
    }


@pytest.fixture
def full_entry() -> dict:
    """A complete entry with all optional fields."""
    return {
        "id": "osworld",
        "name": "OSWorld",
        "version": "1.2.0",
        "description": (
            "Benchmarks multimodal agents on open-ended tasks in a real Ubuntu desktop "
            "environment. Tasks span file management, web browsing, coding, and GUI interaction."
        ),
        "package": "osworld-cube",
        "authors": [
            {"github": "author-a", "name": "Author A"},
            {"github": "author-b", "name": "Author B"},
        ],
        "legal": {
            "wrapper_license": "MIT",
            "benchmark_license": {
                "reported": "CC-BY-4.0",
                "source_url": "https://github.com/xlangai/osworld/blob/main/LICENSE",
                "verified_by_original_authors": False,
            },
            "notices": [
                {
                    "type": "software_registration",
                    "description": "Ubuntu desktop with pre-installed commercial applications",
                }
            ],
        },
        "paper": "https://arxiv.org/abs/2404.07972",
        "tags": ["os", "gui", "desktop", "multimodal"],
        "getting_started_url": "https://os-world.github.io",
        "supported_infra": ["aws", "azure"],
        "max_concurrent_tasks": 1,
        "parallelization_mode": "benchmark-parallel",
        # CI-derived fields (allowed in schema for platform consumers)
        "status": "active",
        "resources": [
            {
                "type": "VMResourceConfig",
                "name": "ubuntu-desktop",
                "image_url": "https://huggingface.co/datasets/xlangai/osworld/resolve/main/ubuntu.qcow2",
                "image_format": "qcow2",
                "image_size_gb": 18.5,
                "ram_gb": 16,
                "disk_gb": 40,
                "gpu": False,
            }
        ],
        "task_count": 369,
        "has_debug_task": True,
        "has_debug_agent": True,
        "action_space": [{"name": "computer", "description": "Mouse, keyboard, and screenshot tool"}],
        "features": {"async": False, "streaming": False, "multi_agent": False, "multi_dim_reward": False},
        "stress_results_url": "stress-results/osworld/v1.2.0.json",
    }


@pytest.fixture
def tmp_owners(tmp_path) -> Path:
    """Create a temporary OWNERS.yaml and return its path."""
    owners = tmp_path / "OWNERS.yaml"
    owners.write_text(
        "# OWNERS.yaml\nosworld:\n  - author-a\n  - author-b\nwebarena:\n  - author-c\n"
    )
    return owners


@pytest.fixture
def tmp_entry(tmp_path, minimal_entry) -> Path:
    """Write a minimal entry YAML to a temp file and return its path."""
    p = tmp_path / "entries" / "my-bench.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(minimal_entry, f)
    return p
