from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class WeddingNotesTests(TestCase):
    def test_search_edit_and_scope(self):
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"ORION_WEDDING_DB": str(Path(directory) / "wedding.db"),
                           "ORION_DB": str(Path(directory) / "orion.db")}
        ):
            try:
                with TestClient(main.app) as api:
                    def create(name):
                        return api.post("/api/wedding/plans", json={
                            "nom": name, "date_mariage": "2027-07-01",
                        }).json()

                    first, second = create("Mariage A"), create("Mariage B")
                    url = f"/api/wedding/plans/{first['id']}/notes"
                    other = f"/api/wedding/plans/{second['id']}/notes"
                    task_id = first["tasks"][0]["id"]
                    note = {"kind": "decision", "title": "Éclairage extérieur",
                            "content": "Guirlandes validées", "source": "Compte rendu",
                            "task_id": task_id}
                    self.assertEqual(api.post(url, json={**note, "task_id": 9999}).status_code, 422)
                    saved = api.post(url, json=note)
                    self.assertEqual(saved.status_code, 201)
                    key = saved.json()["id"]
                    api.post(url, json={**note, "kind": "idea"}).raise_for_status()
                    results = api.get(url, params={"q": "ECLAIRAGE validees", "limit": 1}).json()
                    self.assertTrue(results["has_more"])
                    self.assertEqual(len(results["notes"]), 1)
                    self.assertEqual(api.get(url, params={"q": "compte", "kind": "decision"})
                                     .json()["notes"][0]["task_id"], task_id)
                    self.assertEqual(api.get(other).json()["notes"], [])
                    self.assertEqual(api.put(other + "/" + key, json=note).status_code, 404)
                    api.put(url + "/" + key, json={**note, "title": "Plan lumière"}).raise_for_status()
                    self.assertEqual(api.get(url, params={"q": "lumiere"}).json()["notes"][0]["id"], key)
            finally:
                main.inbox_store.cache_clear()
                main.workflow_memory.cache_clear()
                main.wedding_notes.cache_clear()
                main.wedding_store.cache_clear()
