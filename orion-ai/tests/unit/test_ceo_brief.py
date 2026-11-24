from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class CEOBriefTests(TestCase):
    def test_partial_reports_and_protected_deadlines(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier",
                        "inbox_store", "site_operations", "ceo_briefs", "ceo_jobs", "business_imports", "project_store"):
                self.addCleanup(getattr(main, key).cache_clear)
            today = main.wedding_today()
            api.post("/api/inbox", json={"kind": "decision", "title": "Signer le devis",
                                        "content": "Rappel", "due_date": (today - timedelta(days=1)).isoformat()}).raise_for_status()
            api.post("/api/wedding/plans", json={"nom":"Dossier test",
                                                "date_mariage": (today + timedelta(days=10)).isoformat()}).raise_for_status()
            main.generate_ceo_brief(today - timedelta(days=1))
            report = api.post("/api/ceo/brief").json()
            self.assertEqual(report["sources"], {"Wedding": "ok", "Site web": "ok", "Mémoire": "ok", "Données métier": "ok", "Projets": "ok"})
            self.assertEqual(report["urgent"], 2)
            note = next(item for item in report["items"] if item["source"] == "Mémoire")
            self.assertTrue(note["link"].startswith("#memoire?entree="))
            self.assertTrue(api.get("/api/ceo/brief").json()["previous"])
            with patch.object(main.SiteOperations, "brief_queue", side_effect=ValueError("service de test")):
                with self.assertLogs("core.ceo_brief", level="ERROR"):
                    partial = api.post("/api/ceo/brief").json()
                self.assertEqual(partial["sources"]["Site web"], "error")
                self.assertEqual(partial["count"], 2)
            password = "Mot-de-passe-123"
            main.inbox_accounts().add("admin", password, "admin")
            main.inbox_accounts().add("member", password, "member")
            self.assertEqual(api.get("/api/ceo/brief").status_code, 401)
            self.assertEqual(api.get("/api/ceo/brief", auth=("member", password)).status_code, 403)
            self.assertEqual(api.get("/api/ceo/brief", auth=("admin", password)).status_code, 200)
