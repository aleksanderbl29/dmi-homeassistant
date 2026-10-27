"""Offline checks for compatibility target selection."""

import unittest
from unittest.mock import MagicMock, patch

from ha_compat import DEV_URL, matrix, python_version, requirements, stable_targets


class CompatibilityTests(unittest.TestCase):
    def test_selects_exact_minimum_intermediate_months_and_latest_patch(self):
        releases = {
            "2025.11.9": [{"yanked": False}],
            "2025.12.0": [{"yanked": False}],
            "2025.12.5": [{"yanked": False}],
            "2026.1.0": [{"yanked": False}],
            "2026.2.0": [{"yanked": False}],
            "2026.3.0": [{"yanked": False}],
            "2026.3.4": [{"yanked": False}],
            "2026.4.0": [{"yanked": False}],
            "2026.5.0": [{"yanked": False}],
            "2026.5.2": [{"yanked": False}],
            "2026.6.0": [{"yanked": True}],
            "2026.7.0b1": [{"yanked": False}],
            "2026.8.0": [],
        }
        self.assertEqual(
            stable_targets(releases, "2025.12.0"),
            ["2025.12.0", "2026.2.0", "2026.4.0", "2026.5.2"],
        )

    def test_short_release_history_has_no_duplicate_targets(self):
        self.assertEqual(
            stable_targets({"2025.12.0": [{"yanked": False}]}, "2025.12.0"),
            ["2025.12.0"],
        )

    def test_rejects_missing_supported_releases(self):
        with self.assertRaises(ValueError):
            stable_targets({}, "2025.12.0")

    def test_python_uses_required_minor_with_latest_patch(self):
        self.assertEqual(python_version(">=3.14.2"), "3.14")
        with self.assertRaises(ValueError):
            python_version("unknown")

    def test_historical_environment_can_resolve_matching_fixture_stack(self):
        dependencies = requirements("2025.12.0").splitlines()
        self.assertIn("homeassistant==2025.12.0", dependencies)
        self.assertIn("pytest-homeassistant-custom-component", dependencies)
        self.assertIn("pytest", dependencies)
        self.assertIn("aiohttp>=3.9.0,<4.0.0", dependencies)
        self.assertIn("aioresponses>=0.7", dependencies)
        self.assertEqual(sum(line.startswith("homeassistant") for line in dependencies), 1)

    def test_development_environment_uses_upstream_source(self):
        dependencies = requirements("dev").splitlines()
        self.assertIn(f"homeassistant @ {DEV_URL}", dependencies)
        self.assertIn(
            "pytest-home-assistant @ git+https://github.com/home-assistant/core.git@dev"
            "#subdirectory=packages/pytest-home-assistant",
            dependencies,
        )
        self.assertNotIn("pytest-homeassistant-custom-component", dependencies)

    def test_matrix_separates_historical_current_locked_and_development_jobs(self):
        root = MagicMock()
        files = {
            "hacs.json": '{"homeassistant": "2025.12.0"}',
            "uv.lock": '[[package]]\nname = "homeassistant"\nversion = "2025.12.0"',
        }
        root.__truediv__.side_effect = lambda name: MagicMock(
            read_text=MagicMock(return_value=files[name])
        )
        release = {
            "info": {"requires_python": ">=3.13.2"},
            "urls": [{"upload_time_iso_8601": "2025-12-03T18:00:00Z"}],
        }
        releases = {
            "releases": {
                "2025.12.0": [{"yanked": False}],
                "2026.1.0": [{"yanked": False}],
            }
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'[project]\nrequires-python = ">=3.14.2"'
        )
        with (
            patch("ha_compat.ROOT", root),
            patch("ha_compat.fetch_json", side_effect=[releases, release, release, release]),
            patch("ha_compat.urlopen", return_value=response),
        ):
            rows = matrix()["include"]
        self.assertEqual(rows[0]["version"], "2025.12.0")
        self.assertEqual(rows[0]["cutoff"], "2025-12-10T18:00:00+00:00")
        self.assertEqual(rows[1]["version"], "2026.1.0")
        self.assertEqual(rows[1]["cutoff"], "")
        self.assertEqual(rows[2]["mode"], "locked")
        self.assertEqual(rows[3]["version"], "dev")
        self.assertEqual(rows[3]["python"], "3.14")
        self.assertEqual([row["experimental"] for row in rows], [False, False, False, True])


if __name__ == "__main__":
    unittest.main()
