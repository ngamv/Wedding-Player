from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class WeddingWorkflowSourcesTests(TestCase):
    def test_selected_sources_are_sent_and_preserved_in_wedding_history(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
            "ORION_MODE": "simulation",
        }):
            self.addCleanup(main.workflow_memory.cache_clear)
            self.addCleanup(main.wedding_notes.cache_clear)
            self.addCleanup(main.wedding_store.cache_clear)
            with TestClient(main.app) as api:
                plans = [api.post("/api/wedding/plans", json={
                    "nom": name, "date_mariage": "2027-06-15",
                }).json()["id"] for name in ("A", "B")]
                a, b = (f"/api/wedding/plans/{plan}" for plan in plans)
                note = {"title": "Décision", "content": "Budget validé", "kind": "decision"}
                note_id = api.post(a + "/notes", json=note).json()["id"]
                model = api.get("/api/dashboard/wedding").json()[0]["id"]
                payload = {"template_id": model, "note_ids": [note_id]}
                self.assertEqual(api.post(b + "/workflows", json=payload).status_code, 422)
                with patch.object(main.LLMManager, "complete", return_value="Livrable [S1]") as completion:
                    response = api.post(a + "/workflows", json=payload)
                    self.assertEqual(response.status_code, 201, response.text)
                    self.assertEqual(completion.call_args.args[-1][0]["content"], "Budget validé")
                run = response.json()["id"]
                api.put(a + "/notes/" + note_id, json={**note, "content": "Budget révisé"}).raise_for_status()
                self.assertEqual(api.get(a + "/workflows/" + run).json()["sources"][0]["content"], "Budget validé")
                self.assertEqual(api.get(a + "/workflows").json()[0]["id"], run)
                self.assertEqual(api.get(b + "/workflows/" + run).status_code, 404)
                self.assertEqual(api.get("/api/workflows/" + run).status_code, 404)
                generic = api.post("/api/workflows", json={"task": "Préparer une synthèse"}).json()
                self.assertEqual(api.get("/api/workflows/" + generic["id"]).status_code, 200)
