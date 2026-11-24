import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class WeddingBriefTests(TestCase):
    def test_scheduler_and_manual_brief_share_history(self):
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"ORION_WEDDING_DB": str(Path(directory) / "wedding.db"),
                           "ORION_DB": str(Path(directory) / "orion.db")}
        ):
            try:
                with TestClient(main.app) as api:
                    url = "/api/wedding/brief"
                    today = main.wedding_today()
                    yesterday = today - timedelta(days=1)
                    self.assertIsNone(api.get(url).json()["latest"])
                    path = Path(directory) / "daily.json"
                    subprocess.run([sys.executable, "-m", "backend.wedding_digest", "--date",
                                    yesterday.isoformat(), "--sortie", str(path)],
                                   cwd=main.ROOT, env=os.environ.copy(), check=True)
                    self.assertTrue(path.is_file())
                    self.assertEqual(api.get(url).json()["latest"]["date"], yesterday.isoformat())
                    for _ in range(2):
                        self.assertEqual(api.post(url).status_code, 201)
                    history = api.get(url).json()
                    self.assertEqual(history["latest"]["date"], today.isoformat())
                    self.assertEqual(history["previous"]["date"], yesterday.isoformat())
                    self.assertIsNone(api.get(url + "?jours=14").json()["latest"])
            finally:
                main.inbox_store.cache_clear()
                main.brief_journal.cache_clear()
                main.workflow_memory.cache_clear()
                main.wedding_dossier.cache_clear()
                main.wedding_store.cache_clear()
