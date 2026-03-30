"""
Tests for scripts/health_check.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest
import yaml

from health_check import check_entry, http_head, pip_installable, HealthResult


# ─── http_head ────────────────────────────────────────────────────────────────


class TestHttpHead:
    def test_reachable_200_passes(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("health_check.urlopen", return_value=mock_resp):
            ok, err = http_head("https://example.com/resource.qcow2")
        assert ok is True
        assert err == ""

    def test_reachable_302_passes(self):
        """3xx redirects are acceptable for image URLs (CDNs redirect)."""
        mock_resp = MagicMock()
        mock_resp.status = 302
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("health_check.urlopen", return_value=mock_resp):
            ok, err = http_head("https://cdn.example.com/image.qcow2")
        assert ok is True

    def test_404_fails(self):
        with patch("health_check.urlopen", side_effect=HTTPError(
            "https://example.com/gone.qcow2", 404, "Not Found", {}, None
        )):
            ok, err = http_head("https://example.com/gone.qcow2")
        assert ok is False
        assert "404" in err

    def test_503_fails(self):
        with patch("health_check.urlopen", side_effect=HTTPError(
            "https://example.com", 503, "Service Unavailable", {}, None
        )):
            ok, err = http_head("https://example.com")
        assert ok is False
        assert "503" in err

    def test_connection_error_fails(self):
        with patch("health_check.urlopen", side_effect=URLError("Connection refused")):
            ok, err = http_head("https://unreachable.example.com/image.qcow2")
        assert ok is False
        assert "Connection refused" in err or "URL error" in err

    def test_generic_exception_fails(self):
        with patch("health_check.urlopen", side_effect=Exception("timeout")):
            ok, err = http_head("https://example.com")
        assert ok is False
        assert "timeout" in err


# ─── pip_installable ─────────────────────────────────────────────────────────


class TestPipInstallable:
    def test_installable_package_passes(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("health_check.subprocess.run", return_value=mock_result):
            ok, err = pip_installable("my-package", "1.0.0")
        assert ok is True

    def test_uninstallable_package_fails(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: No matching distribution found for my-package==1.0.0"
        with patch("health_check.subprocess.run", return_value=mock_result):
            ok, err = pip_installable("my-package", "1.0.0")
        assert ok is False
        assert "No matching distribution" in err or "pip install" in err

    def test_timeout_fails(self):
        import subprocess
        with patch("health_check.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=60)):
            ok, err = pip_installable("slow-package", "1.0.0")
        assert ok is False
        assert "timed out" in err.lower()

    def test_unexpected_exception_fails(self):
        with patch("health_check.subprocess.run", side_effect=RuntimeError("unexpected")):
            ok, err = pip_installable("bad-package", "1.0.0")
        assert ok is False
        assert "unexpected" in err


# ─── check_entry ─────────────────────────────────────────────────────────────


class TestCheckEntry:
    def _write_entry(self, tmp_path: Path, entry: dict) -> Path:
        p = tmp_path / "entries" / f"{entry['id']}.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            yaml.dump(entry, f)
        return p

    def _base_entry(self) -> dict:
        return {
            "id": "test-bench",
            "name": "Test Benchmark",
            "version": "1.0.0",
            "description": "A test benchmark.",
            "package": "test-bench-cube",
            "authors": [{"github": "author1"}],
            "legal": {"wrapper_license": "MIT"},
            "status": "active",
        }

    def test_healthy_entry_passes(self, tmp_path):
        entry = self._base_entry()
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(True, ""))
        with patch("health_check.pip_installable", mock_pip):
            result = check_entry(entry_path)

        assert result.passed is True
        assert result.failures == []

    def test_pip_failure_reported(self, tmp_path):
        entry = self._base_entry()
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(False, "No matching distribution found"))
        with patch("health_check.pip_installable", mock_pip):
            result = check_entry(entry_path)

        assert result.passed is False
        assert any("pip install" in f for f in result.failures)

    def test_unreachable_image_url_fails(self, tmp_path):
        entry = self._base_entry()
        entry["resources"] = [
            {
                "type": "VMResourceConfig",
                "image_url": "https://example.com/ubuntu.qcow2",
            }
        ]
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(True, ""))
        mock_head = MagicMock(return_value=(False, "HTTP 404"))
        with patch("health_check.pip_installable", mock_pip), \
             patch("health_check.http_head", mock_head):
            result = check_entry(entry_path)

        assert result.passed is False
        assert any("image URL" in f or "unreachable" in f.lower() for f in result.failures)

    def test_reachable_image_url_passes(self, tmp_path):
        entry = self._base_entry()
        entry["resources"] = [
            {
                "type": "VMResourceConfig",
                "image_url": "https://huggingface.co/datasets/xlangai/osworld/ubuntu.qcow2",
            }
        ]
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(True, ""))
        mock_head = MagicMock(return_value=(True, ""))
        with patch("health_check.pip_installable", mock_pip), \
             patch("health_check.http_head", mock_head):
            result = check_entry(entry_path)

        assert result.passed is True

    def test_dead_license_url_fails(self, tmp_path):
        entry = self._base_entry()
        entry["legal"]["benchmark_license"] = {
            "reported": "MIT",
            "source_url": "https://example.com/LICENSE",
        }
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(True, ""))
        mock_head = MagicMock(return_value=(False, "HTTP 404"))
        with patch("health_check.pip_installable", mock_pip), \
             patch("health_check.http_head", mock_head):
            result = check_entry(entry_path)

        assert result.passed is False
        assert any("license" in f.lower() for f in result.failures)

    def test_archived_entry_skipped(self, tmp_path):
        entry = self._base_entry()
        entry["status"] = "archived"
        entry_path = self._write_entry(tmp_path, entry)

        with patch("health_check.pip_installable") as mock_pip:
            result = check_entry(entry_path)
            # pip_installable should NOT be called for archived entries
            mock_pip.assert_not_called()

        assert result.passed is True

    def test_multiple_resources_all_checked(self, tmp_path):
        entry = self._base_entry()
        entry["resources"] = [
            {"type": "VMResourceConfig", "image_url": "https://example.com/image1.qcow2"},
            {"type": "VMResourceConfig", "image_url": "https://example.com/image2.qcow2"},
        ]
        entry_path = self._write_entry(tmp_path, entry)

        pip_mock = MagicMock(return_value=(True, ""))
        # First URL passes, second fails
        head_mock = MagicMock(side_effect=[(True, ""), (False, "HTTP 404")])

        with patch("health_check.pip_installable", pip_mock), \
             patch("health_check.http_head", head_mock):
            result = check_entry(entry_path)

        assert result.passed is False
        assert len(result.failures) == 1

    def test_entry_id_from_path_stem(self, tmp_path):
        entry = self._base_entry()
        entry_path = self._write_entry(tmp_path, entry)

        mock_pip = MagicMock(return_value=(True, ""))
        with patch("health_check.pip_installable", mock_pip):
            result = check_entry(entry_path)

        assert result.entry_id == "test-bench"
