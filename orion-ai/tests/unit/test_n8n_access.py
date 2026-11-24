import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from core.n8n_access import USERNAME, configure
from scripts.orion_n8n import WORKFLOW, bind_workflow


class N8nAccessTests(TestCase):
    def test_service_credential_only_allows_wedding_reports(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
            "ORION_RECOVERY": "0",
        }), TestClient(main.app) as api:
            for name in ("workflow_memory", "inbox_store", "wedding_store", "wedding_dossier", "brief_journal"):
                self.addCleanup(getattr(main, name).cache_clear)
            main.inbox_accounts().add("admin", "Mot-de-passe-123", "admin")
            token = "test-service-token"
            configure(main.workflow_memory().path, token)
            credentials = (USERNAME, token)
            self.assertEqual(api.get("/api/wedding/daily-report").status_code, 401)
            self.assertEqual(api.get("/api/wedding/daily-report", auth=credentials).status_code, 200)
            self.assertEqual(api.post("/api/wedding/brief?source=n8n", auth=credentials).status_code, 201)
            self.assertEqual(api.get("/api/wedding/plans", auth=credentials).status_code, 401)
            self.assertEqual(api.get("/api/sites", auth=credentials).status_code, 401)
            with patch.dict("os.environ", {"ORION_RECOVERY": "1"}):
                self.assertEqual(api.get("/api/wedding/daily-report", auth=credentials).status_code, 401)

    def test_binding_keeps_custom_nodes_without_attaching_credentials(self):
        template = json.loads(WORKFLOW.read_text())
        workflow = json.loads(WORKFLOW.read_text())
        workflow["nodes"].append({"name":"Étape locale", "type":"custom", "parameters":{"url":"https://example.com"}})
        first = bind_workflow(workflow, "http://127.0.0.1:8001", template)
        again = bind_workflow(first, "http://127.0.0.1:8001", template)
        self.assertEqual(len(again["connections"]["Lire le rapport ORION"]["main"][0]), 1)
        self.assertNotIn("credentials", again["nodes"][-1])
        requests = [node for node in again["nodes"] if node["type"] == "n8n-nodes-base.httpRequest"]
        self.assertTrue(all(node["parameters"]["url"].startswith("http://127.0.0.1:8001/api/wedding/")
                            and "httpBasicAuth" in node["credentials"] for node in requests))
