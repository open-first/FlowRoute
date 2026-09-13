import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from flowroute.models import CatalogSnapshot
from flowroute.registry import CatalogVersionError, WorkflowRegistry

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")

    def test_catalog_is_loaded_and_hashed(self):
        self.assertEqual(self.registry.catalog_version, "demo-2026-09-04")
        self.assertEqual(len(self.registry.content_hash), 64)
        self.assertGreaterEqual(len(self.registry.active_workflows()), 7)

    def test_version_mismatch_is_rejected(self):
        with self.assertRaises(CatalogVersionError):
            self.registry.require_version("stale-version")

    def test_exact_event_mapping_is_unique(self):
        workflow = self.registry.event_workflow("user_registered")
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.id, "communications.send_welcome_email")

    def test_catalog_file_size_limit_is_enforced_before_parsing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.yaml"
            path.write_text("x" * 2_000, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "catalog exceeds"):
                WorkflowRegistry.from_yaml(path, max_bytes=1_024)

    def test_production_issues_include_missing_owner(self):
        registry = WorkflowRegistry(
            CatalogSnapshot(
                catalog_version="test",
                workflows=[
                    {
                        "id": "records.lookup",
                        "version": "1.0.0",
                        "name": "Look up record",
                        "description": "Look up one record using its stable identifier.",
                    }
                ],
            )
        )
        self.assertEqual(
            registry.production_issues(),
            ["records.lookup: production workflows must declare an owner"],
        )


if __name__ == "__main__":
    unittest.main()
