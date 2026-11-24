import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from scripts.orion_backup import backup, restore


class LocalOperationsTests(TestCase):
    def test_backup_restore_and_failure_journal(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("brief_journal", "workflow_memory", "wedding_dossier", "wedding_store"):
                self.addCleanup(getattr(main, name).cache_clear)
            with patch.dict("os.environ", {
                "ORION_DB": str(directory / "source.db"),
                "ORION_WEDDING_DB": str(directory / "events.db"),
            }), TestClient(main.app) as api:
                api.post("/api/wedding/plans", json={"nom": "Mariage restauration", "date_mariage": "2027-07-01"}).raise_for_status()
                with patch.object(main.WeddingDossier, "overview", side_effect=ValueError("incident simulé")):
                    self.assertEqual(api.post("/api/wedding/brief?source=n8n").status_code, 422)
                self.assertEqual(main.brief_journal().latest()[0]["state"], "failed")
                api.post("/api/wedding/brief").raise_for_status()
                archive = directory / "backup.zip"
                backup(archive)
                recovered = directory / "recovered"
                restore(archive, recovered)
                with self.assertRaises(FileExistsError):
                    restore(archive, recovered)
                with closing(sqlite3.connect(recovered / "orion.sqlite3")) as db:
                    self.assertEqual(db.execute("SELECT state FROM wedding_brief_runs ORDER BY id").fetchall(),
                                     [("failed",), ("completed",)])
                with closing(sqlite3.connect(recovered / "wedding.sqlite3")) as db:
                    self.assertEqual(db.execute("SELECT nom FROM wedding_plans").fetchone()[0], "Mariage restauration")
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM wedding_briefs").fetchone()[0], 1)
