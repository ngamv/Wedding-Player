from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class InboxTests(TestCase):
    def test_capture_link_search_and_export(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for name in ("inbox_store", "workflow_memory", "wedding_store", "site_operations", "project_store"):
                self.addCleanup(getattr(main, name).cache_clear)
            plan = api.post("/api/wedding/plans", json={"nom": "Mariage test", "date_mariage": "2027-07-01"}).json()
            site = api.post("/api/sites", json={"name": "Site test", "url": "https://example.com"}).json()
            note = {"kind": "decision", "title": "Éclairage retenu", "content": "Guirlandes validées",
                    "source": "Réunion client", "source_date": "2026-11-23", "due_date": "2027-06-01"}
            href = "/api/inbox"
            response = api.post(href, json=note)
            self.assertEqual(response.status_code, 201)
            path = href + "/" + response.json()["id"]
            self.assertEqual(len(api.get(href, params={"scope": "unfiled"}).json()["items"]), 1)
            self.assertEqual(api.put(path, json={**note, "target_kind": "wedding"}).status_code, 422)
            linked = {**note, "target_kind": "wedding", "target_id": plan["id"]}
            api.put(path, json=linked).raise_for_status()
            self.assertEqual(len(api.get(href + "/targets").json()), 2)
            self.assertEqual(api.get(href, params={"scope": "site:" + site["id"]}).json()["items"], [])
            matches = api.get(href, params={"q": "eclairage validees", "scope": "wedding:" + plan["id"]})
            self.assertEqual(matches.json()["items"][0]["source_date"], note["source_date"])
            exported = api.get(href + "/export")
            self.assertIn("attachment", exported.headers["content-disposition"])
            self.assertEqual(exported.json()["items"][0]["target_id"], plan["id"])
