from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class ProjectsTests(TestCase):
    def test_blocked_project_is_linked_in_brief_until_completed(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"),
            "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier", "inbox_store",
                        "site_operations", "ceo_briefs", "ceo_jobs", "business_imports", "project_store"):
                self.addCleanup(getattr(main, key).cache_clear)
            form = {"title": "Livraison test", "owner": "Équipe", "status": "blocked"}
            self.assertEqual(api.post("/api/projects", json=form).status_code, 422)
            created = api.post("/api/projects", json={**form, "note": "Validation attendue"}).json()
            self.assertEqual(api.get("/api/projects?status=active").json(), [])
            brief = api.post("/api/ceo/brief").json()
            item = next(row for row in brief["items"] if row["source"] == "Projets")
            self.assertEqual(item["level"], 0)
            self.assertEqual(item["link"], "#projets?projet=" + created["id"])
            overview = api.get("/api/dashboard/overview").json()
            self.assertEqual(overview["blocked_projects"], 1)
            self.assertIsNone(overview["receipts_source"])
            self.assertEqual(overview["brief"]["items"][0]["link"], item["link"])
            result = api.put("/api/projects/" + created["id"],
                             json={**form, "status": "done", "note": "Livré"}).json()
            self.assertEqual(len(result["history"]), 2)
            updated = api.post("/api/ceo/brief").json()
            self.assertFalse(any(row["source"] == "Projets" for row in updated["items"]))

            another = api.post("/api/projects", json={**form, "title":"Autre projet", "status":"active"}).json()
            project = "/api/projects/" + another["id"]
            task = {"title":"Recette", "owner":"QA", "status":"blocked", "note":"Données attendues"}
            saved = api.post(project + "/tasks", json=task)
            self.assertEqual(saved.status_code, 201)
            task_id = saved.json()["tasks"][0]["id"]
            wrong = "/api/projects/" + created["id"] + "/tasks/" + task_id
            self.assertEqual(api.put(wrong, json=task).status_code, 404)
            alert = next(row for row in api.post("/api/ceo/brief").json()["items"] if row["source"]=="Projets")
            self.assertEqual(alert["level"], 0)
            self.assertIn("1 tâche(s) bloquée(s)", alert["detail"])
            api.put(project + "/tasks/" + task_id, json={**task, "status":"done"}).raise_for_status()
            self.assertFalse(any(row["source"] == "Projets" for row in api.post("/api/ceo/brief").json()["items"]))

    def test_project_memory_is_scoped_and_protected(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_MODE": "ollama",
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "inbox_store", "project_store"):
                self.addCleanup(getattr(main, key).cache_clear)
            projects = [api.post("/api/projects", json={"title": title, "owner": "Équipe",
                       "status": "active"}).json()["id"] for title in ("Alpha", "Bêta")]
            alpha, beta = projects
            note = {"kind": "decision", "title": "Validation", "content": "Budget confirmé",
                    "source_date": "2026-11-24", "target_kind": "project", "target_id": alpha}
            response = api.post("/api/inbox", json=note)
            self.assertEqual(response.status_code, 201)
            entry = response.json()["id"]
            url = "/api/projects/" + alpha + "/memory"
            self.assertEqual(api.get(url).json()["items"][0]["id"], entry)
            self.assertEqual(api.get(f"/api/projects/{beta}/memory").json()["items"], [])
            self.assertEqual(api.post("/api/inbox", json={**note, "target_id":"0"*32}).status_code, 404)
            with patch.object(main.LLMManager, "complete", return_value="Budget confirmé [S1]") as llm:
                answer = api.post("/api/inbox/question", json={"scope": "project:" + alpha,
                                  "question": "Quelle est la décision ?"}).json()
                self.assertEqual(answer["sources"][0]["date"], "2026-11-24")
                self.assertEqual(llm.call_args.args[-1][0]["id"], entry)
            password = "Mot-de-passe-123"
            main.inbox_accounts().add("admin", password, "admin")
            main.inbox_accounts().add("member", password, "member")
            auth = ("member", password)
            self.assertEqual(api.get(url, auth=auth).status_code, 403)
            self.assertEqual(api.post("/api/inbox", auth=auth, json=note).status_code, 403)

    def test_task_dependencies_prevent_cycles_and_inconsistent_completion(self):
        from datetime import date
        from core.projects import Projects

        with TemporaryDirectory() as tmp:
            store = Projects(Path(tmp) / "projects.db")
            item = {"title":"Mise en ligne", "owner":"Équipe", "due":"2026-11-25",
                    "status":"planned", "note":""}
            project = store.save({**item, "due":None}, "Local")["id"]
            plan = store.save_task(project, {**item, "title":"Recette"}, "Local")
            prerequisite = plan["tasks"][0]["id"]
            plan = store.save_task(project, item, "Local", dependencies=[prerequisite])
            task = next(row for row in plan["tasks"] if row["id"] != prerequisite)
            self.assertEqual(task["waiting_for"], [prerequisite])
            self.assertEqual(store.priorities(date(2026, 11, 24), date(2026, 11, 30))[0]["waiting_tasks"], 1)
            with self.assertRaisesRegex(ValueError, "boucle"):
                store.save_task(project, item, "Local", prerequisite, [task["id"]])
            with self.assertRaisesRegex(ValueError, "prérequis"):
                store.save_task(project, {**item, "status":"done"}, "Local", task["id"])
            store.save_task(project, {**item, "status":"done"}, "Local", prerequisite)
            store.save_task(project, {**item, "status":"done"}, "Local", task["id"])
            with self.assertRaisesRegex(ValueError, "Rouvrez"):
                store.save_task(project, item, "Local", prerequisite)

    def test_planning_filters_exclude_completed_work(self):
        from datetime import date
        from core.projects import Projects

        with TemporaryDirectory() as tmp:
            store = Projects(Path(tmp) / "projects.db")
            today = date(2026, 11, 24)
            base = {"title":"Livraison", "owner":"Équipe", "due":None, "status":"active", "note":""}
            project = store.save(base, "Local")["id"]
            closed = store.save({**base, "status":"done"}, "Local")["id"]
            store.save_task(project, {**base, "title":"Recette", "owner":"QA", "due":"2026-11-23"}, "Local")
            store.save_task(project, {**base, "title":"Mise en ligne", "due":"2026-11-25", "status":"blocked"}, "Local")
            store.save_task(closed, {**base, "title":"Ancienne", "due":"2026-11-20"}, "Local")
            store.save_task(project, {**base, "title":"Terminée", "status":"done"}, "Local")
            report = store.planning(today, "overdue", "QA", 10, 0)
            self.assertEqual([row["title"] for row in report["items"]], ["Recette"])
            self.assertEqual(report["counts"]["total"], 1)
            report = store.planning(today, "blocked", "", 10, 0)
            self.assertEqual([row["title"] for row in report["items"]], ["Mise en ligne"])
            self.assertEqual(report["counts"]["total"], 2)
            self.assertEqual(report["counts"]["upcoming"], 1)
