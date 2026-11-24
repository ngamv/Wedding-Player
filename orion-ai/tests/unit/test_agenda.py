from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class AgendaTests(TestCase):
    def test_agenda_combines_sources_and_removes_completed_items(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier",
                        "inbox_store", "project_store", "business_imports"):
                self.addCleanup(getattr(main, key).cache_clear)
            project = api.post("/api/projects", json={"title":"Livraison","owner":"Coordination",
                               "due":"2026-11-25","status":"active"}).json()["id"]
            task = {"title":"Recette","owner":"QA","due":"2026-11-26","status":"planned"}
            api.post(f"/api/projects/{project}/tasks", json=task).raise_for_status()
            api.post(f"/api/projects/{project}/tasks", json={**task, "title":"Terminé","status":"done"}).raise_for_status()
            api.post("/api/wedding/plans", json={"nom":"Mariage", "date_mariage":"2026-11-27"}).raise_for_status()
            api.post("/api/ceo/imports/appointments", json={"content":
                     "id,title,date,status\nA,Rendez-vous,2026-11-24,scheduled\nB,Annulé,2026-11-25,cancelled"}).raise_for_status()
            response = api.get("/api/agenda", params={"start":"2026-11-24","days":4})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([row["kind"] for row in response.json()["items"]],
                             ["appointment", "project", "task", "wedding"])
            url = api.get("/api/agenda", params={"start":"2026-11-24","days":4,"kind":"task"}).json()["items"][0]["link"]
            self.assertIn("tache=", url)
