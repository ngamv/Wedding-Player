from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class DashboardSessionTests(TestCase):
    def test_cookie_unlocks_modules_and_logout_revokes_it(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB":str(Path(tmp) / "orion.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "inbox_store", "project_store", "business_imports"):
                self.addCleanup(getattr(main, key).cache_clear)
            password = "Mot-de-passe-123"
            main.inbox_accounts().add("admin", password, "admin")
            self.assertEqual(api.get("/api/projects").status_code, 401)
            auth = api.post("/api/session", json={"username":"admin","password":password})
            self.assertEqual(auth.status_code, 200)
            cookie = auth.headers["set-cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=strict", cookie)
            self.assertEqual(api.get("/api/projects").status_code, 200)
            self.assertEqual(api.get("/api/finance/receipts").status_code, 200)
            project = {"title":"Dossier","owner":"Équipe","status":"active"}
            self.assertEqual(api.post("/api/projects", json=project,
                             headers={"Origin":"http://testserver:6000", "Sec-Fetch-Site":"same-site"}).status_code, 403)
            self.assertEqual(api.post("/api/projects", json=project).status_code, 201)
            saved = next(iter(api.cookies.items()))
            api.delete("/api/session").raise_for_status()
            self.assertEqual(api.get("/api/projects").status_code, 401)
            self.assertEqual(api.get("/api/projects", headers={"Cookie":"=".join(saved)}).status_code, 401)

    def test_legacy_modules_require_administrator_when_accounts_are_enabled(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB":str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB":str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "inbox_store", "wedding_store", "site_operations"):
                self.addCleanup(getattr(main, key).cache_clear)
            site = {"name":"Projet confidentiel", "url":"https://example.com"}
            api.post("/api/sites", json=site).raise_for_status()
            password = "Mot-de-passe-123"
            accounts = main.inbox_accounts()
            accounts.add("admin", password, "admin")
            accounts.add("member", password, "member")

            for path in ("/api/sites", "/api/wedding/plans", "/api/wedding/daily-report",
                         "/api/workflows/test", "/api/memory/search?q=test", "/api/dashboard/local-operations"):
                self.assertEqual(api.get(path).status_code, 401, path)
                self.assertEqual(api.get(path, auth=("member", password)).status_code, 403, path)
            self.assertEqual(api.get("/api/inbox/targets", auth=("member", password)).json(), [])
            self.assertEqual(api.get("/api/dashboard/status").status_code, 200)
            self.assertEqual(api.get("/api/wedding/daily-report", auth=("admin", password)).status_code, 200)
            api.post("/api/session", json={"username":"admin","password":password}).raise_for_status()
            self.assertEqual(api.get("/api/sites").json()["sites"][0]["name"], site["name"])
            self.assertEqual(api.post("/api/workflows", json={"task":"Rédiger un point."},
                                     headers={"Origin":"http://testserver:7777"}).status_code, 403)
