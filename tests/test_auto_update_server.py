import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "auto_update_server.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("auto_update_server", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class StopAfterOneRefresh:
    def __init__(self):
        self.wait_calls = []

    def wait(self, interval):
        self.wait_calls.append(interval)
        return len(self.wait_calls) > 1


class AutoUpdateServerTests(unittest.TestCase):
    def test_refresh_catalog_writes_both_data_files(self):
        projects = [{"name": "Example", "url": "https://example.com"}]
        sources = [{"id": "example/source", "contributed_count": 1}]

        with tempfile.TemporaryDirectory() as directory:
            projects_path = Path(directory) / "projects.json"
            sources_path = Path(directory) / "sources.json"
            with (
                patch.object(MODULE, "PROJECTS_PATH", projects_path),
                patch.object(MODULE, "SOURCES_PATH", sources_path),
                patch.object(MODULE, "build_catalog", return_value=(projects, sources)),
            ):
                MODULE.refresh_catalog()

            self.assertIn('"Example"', projects_path.read_text(encoding="utf-8"))
            self.assertIn('"example/source"', sources_path.read_text(encoding="utf-8"))

    def test_update_loop_refreshes_after_each_interval(self):
        stop_event = StopAfterOneRefresh()

        with patch.object(MODULE, "refresh_catalog") as refresh_catalog:
            MODULE.update_loop(60, stop_event)

        refresh_catalog.assert_called_once_with()
        self.assertEqual(stop_event.wait_calls, [60, 60])


if __name__ == "__main__":
    unittest.main()
