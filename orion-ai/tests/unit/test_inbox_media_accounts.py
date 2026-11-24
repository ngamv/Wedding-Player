import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class InboxMediaAccountsTests(TestCase):
    def test_isolation_and_source_references(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_MODE": "ollama",
        }), TestClient(main.app) as api:
            for name in ("inbox_store", "workflow_memory"):
                self.addCleanup(getattr(main, name).cache_clear)
            password = "Local-a-test-123"
            accounts = main.inbox_accounts()
            for username, role in (("alice", "admin"), ("camille", "member"), ("sam", "member")):
                accounts.add(username, password, role)
            alice, camille, sam = [(user, password) for user in ("alice", "camille", "sam")]
            self.assertEqual(api.get("/api/inbox").status_code, 401)
            payload = b"%PDF-1.7\n illustration"
            meta = {"title": "Décision réunion", "kind": "document", "source_date": "2026-11-23"}
            with patch.object(main, "extract_media", return_value=("test.pdf", "application/pdf", "Budget validé", None)):
                imported = api.post("/api/inbox/import", auth=camille, data={"metadata": json.dumps(meta)},
                                    files={"file": ("test.pdf", payload, "application/pdf")})
            self.assertEqual(imported.status_code, 201, imported.text)
            entry_id = imported.json()["id"]
            file = f"/api/inbox/{entry_id}/attachment"
            self.assertEqual(api.get(file, auth=camille).content, payload)
            self.assertEqual(api.get(file, auth=sam).status_code, 404)
            self.assertEqual(api.get("/api/inbox/export", auth=sam).json()["items"], [])
            self.assertEqual(len(api.get("/api/inbox/export", auth=alice).json()["items"]), 1)
            self.assertEqual(api.put(f"/api/inbox/{entry_id}", auth=sam,
                                     json={**meta, "content": "intrus"}).status_code, 404)
            request = {"query": "budget", "question": "Qu’a-t-on décidé ?"}
            with patch.object(main.LLMManager, "complete", return_value="Budget validé [S1]") as llm:
                response = api.post("/api/inbox/question", auth=camille, json=request)
                self.assertEqual(response.json()["sources"][0]["date"], "2026-11-23")
                self.assertEqual(llm.call_args.args[-1][0]["content"], "Budget validé")
                self.assertEqual(api.post("/api/inbox/question", auth=sam, json=request).json()["sources"], [])
            with patch.object(main.LLMManager, "complete", return_value="Réponse inventée [S9]"):
                self.assertEqual(api.post("/api/inbox/question", auth=camille, json=request).status_code, 502)
