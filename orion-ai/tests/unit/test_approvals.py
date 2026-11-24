from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class ApprovalTests(TestCase):
    def test_live_queue_excludes_processed_and_outdated_items(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
            "ORION_MODE": "ollama",
        }), TestClient(main.app) as api:
            for name in ("workflow_memory", "inbox_store", "site_operations", "wedding_store", "wedding_dossier"):
                self.addCleanup(getattr(main, name).cache_clear)
            site = api.post("/api/sites", json={"name":"Atelier","url":"https://example.com"}).json()["id"]
            path = f"/api/sites/{site}/interventions"
            with patch.object(main.LLMManager, "complete", return_value="Plan à examiner"):
                intervention = api.post(path, json={"template":"audit","brief":"Revoir l’accès."}).json()["intervention"]
            project = api.post("/api/wedding/plans", json={"nom":"Mariage", "date_mariage":"2027-07-01"}).json()["id"]
            event = f"/api/wedding/plans/{project}"
            due = main.wedding_today().isoformat()
            guest = {"name":"Invité","email":"guest@example.com","status":"pending","due":due}
            key = api.put(event+"/dossier", json={"kind":"guest","data":guest}).json()["id"]
            api.post(event+"/relances").raise_for_status()
            approvals = api.get("/api/approvals").json()["items"]
            self.assertEqual([item["source"] for item in approvals], ["wedding","site"])
            self.assertIn("relance=guest", approvals[0]["href"])
            self.assertIn(intervention["id"], approvals[1]["href"])
            self.assertNotIn("guest@example.com", str(approvals))

            api.put(event+"/dossier", json={"kind":"guest","id":key,"data":{**guest,"status":"yes"}}).raise_for_status()
            api.patch(path+"/"+intervention["id"], json={"action":"approve"}).raise_for_status()
            self.assertEqual(api.get("/api/approvals").json()["count"], 0)

            followup = api.get("/api/approvals", params={"stage":"followup"}).json()["items"]
            self.assertEqual([(row["source"], row["state"]) for row in followup], [("site", "approved")])
            api.patch(path+"/"+intervention["id"], json={"action":"verify","result":"Contrôle effectué."}).raise_for_status()
            self.assertEqual(api.get("/api/approvals?stage=followup").json()["count"], 0)

            with patch.object(main.LLMManager, "complete", return_value="Autre plan"):
                rejected = api.post(path, json={"template":"audit","brief":"Autre piste."}).json()["intervention"]
            rejected_path = path + "/" + rejected["id"]
            self.assertEqual(api.patch(rejected_path, json={"action":"reject","result":" "}).status_code, 422)
            rejected_state = api.patch(rejected_path, json={"action":"reject","result":"Budget insuffisant."}).json()
            self.assertEqual(rejected_state["state"], "rejected")
            self.assertEqual(api.get(rejected_path).json()["intervention"]["result"], "Budget insuffisant.")
            self.assertEqual(api.patch(rejected_path, json={"action":"approve"}).status_code, 422)
            self.assertEqual(api.get("/api/approvals").json()["count"], 0)

            history = api.get("/api/approvals?stage=history").json()["items"]
            self.assertEqual({item["state"] for item in history}, {"approved","verified","rejected"})
            self.assertTrue(all(item["date"] == due for item in history))
            self.assertNotIn("Budget insuffisant", str(history))
