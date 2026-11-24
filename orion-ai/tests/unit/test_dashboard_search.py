from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class DashboardSearchTests(TestCase):
    def test_results_link_to_records_and_do_not_return_source_body(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "inbox_store",
                        "project_store", "business_imports", "site_operations"):
                self.addCleanup(getattr(main, key).cache_clear)
            project = api.post("/api/projects", json={
                "title":"Éclairage", "owner":"Équipe", "status":"active",
            }).json()["id"]
            api.post(f"/api/projects/{project}/tasks", json={
                "title":"Recette", "owner":"QA", "status":"active",
            }).raise_for_status()
            api.post("/api/inbox", json={
                "title":"Décision", "kind":"note", "content":"Éclairage privé retenu",
            }).raise_for_status()
            url = "/api/dashboard/search"
            results = api.get(url, params={"q":"eclairage"}).json()["items"]
            self.assertEqual([row["kind"] for row in results], ["project","document","task"])
            self.assertNotIn("privé", str(results))
            match = api.get(url, params={"q":"recette","kind":"task"}).json()["items"][0]
            self.assertIn(f"projet={project}&tache=", match["href"])
            self.assertEqual(api.get(url, params={"q":"   "}).status_code, 422)
