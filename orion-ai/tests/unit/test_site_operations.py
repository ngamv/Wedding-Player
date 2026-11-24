from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class SiteOperationsTests(TestCase):
    def test_site_sync_and_intervention(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_MODE": "simulation",
        }):
            self.addCleanup(main.site_operations.cache_clear)
            self.addCleanup(main.workflow_memory.cache_clear)
            with TestClient(main.app) as api:
                form = {"name": "Site de test", "url": "https://example.com", "repo": "org/site"}
                a = api.post("/api/sites", json=form)
                self.assertEqual(a.status_code, 201)
                site_id = a.json()["id"]
                path = f"/api/sites/{site_id}"

                metadata = {"full_name": "org/site", "default_branch": "main",
                            "pushed_at": None, "archived": False}
                with patch("core.site_operations.github_metadata", return_value=metadata):
                    synced = api.post(path + "/github")
                    self.assertEqual(synced.json()["github"], metadata)
                updated = api.put(path, json={**form, "repo": "org/second"})
                self.assertIsNone(updated.json()["github"])

                history = path + "/interventions"
                payload = {"template": "mise-en-ligne", "brief": "Préparer la recette."}
                simulated = api.post(history, json=payload).json()
                self.assertEqual(simulated["intervention"]["state"], "simulation")
                simulation_url = history + "/" + simulated["intervention"]["id"]
                self.assertEqual(api.patch(simulation_url, json={"action": "approve"}).status_code, 422)

                with patch.dict("os.environ", {"ORION_MODE": "ollama"}), patch.object(
                    main.LLMManager, "complete", return_value="Checklist à valider",
                ):
                    prepared = api.post(history, json=payload)
                self.assertEqual(prepared.status_code, 201, prepared.text)
                result = prepared.json()
                row = history + "/" + result["intervention"]["id"]
                check = {"action": "verify", "result": "Recette et retour arrière vérifiés."}
                self.assertEqual(api.patch(row, json=check).status_code, 422)
                self.assertEqual(api.patch(row, json={"action": "approve"}).json()["state"], "approved")
                self.assertEqual(api.patch(row, json=check).json()["state"], "verified")
                self.assertEqual(api.get(row).json()["intervention"]["result"], check["result"])
                self.assertEqual(api.get("/api/workflows/" + result["run"]["id"]).status_code, 404)
                self.assertEqual(len(api.get(history).json()), 2)
