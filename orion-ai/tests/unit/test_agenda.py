from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class AgendaTests(TestCase):
    def test_agenda_combines_sources_and_removes_completed_items(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier",
                        "inbox_store", "project_store", "business_imports"):
                self.addCleanup(getattr(main, key).cache_clear)
            project = api.post("/api/projects", json={"title":"Livraison","owner":"Coordination",
                               "due":"2026-11-25","status":"active"}).json()["id"]
            task = {"title":"Recette","owner":"QA","due":"2026-11-26","status":"planned"}
            api.post(f"/api/projects/{project}/tasks", json=task).raise_for_status()
            api.post(f"/api/projects/{project}/tasks", json={**task, "title":"Terminé","status":"done"}).raise_for_status()
            api.post("/api/wedding/plans", json={"nom":"Mariage", "date_mariage":"2026-11-27"}).raise_for_status()
            api.post("/api/ceo/imports/appointments", json={"content":
                     "id,title,date,status\nA,Rendez-vous,2026-11-24,scheduled\nB,Annulé,2026-11-25,cancelled"}).raise_for_status()
            response = api.get("/api/agenda", params={"start":"2026-11-24","days":4})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([row["kind"] for row in response.json()["items"]],
                             ["appointment", "project", "task", "wedding"])
            url = api.get("/api/agenda", params={"start":"2026-11-24","days":4,"kind":"task"}).json()["items"][0]["link"]
            self.assertIn("tache=", url)

            exported = api.get("/api/agenda/export.ics", params={"start":"2026-11-24","days":4,"kind":"task"})
            self.assertEqual(exported.status_code, 200)
            self.assertEqual(exported.headers["content-type"], "text/calendar; charset=utf-8")
            self.assertIn('orion-agenda-2026-11-24.ics', exported.headers["content-disposition"])
            self.assertIn(b"DTSTART;VALUE=DATE:20261126\r\n", exported.content)
            self.assertIn(b"SUMMARY:Recette\r\n", exported.content)
            self.assertNotIn(b"SUMMARY:Mariage", exported.content)

    def test_calendar_escapes_and_folds_utf8(self):
        from core.agenda import export_calendar
        event = {"id":"a", "kind":"project", "title":"É"*60+"; x, y\r\nBEGIN:VEVENT",
                 "date":"2026-11-25","detail":""}
        original = export_calendar([event])
        shifted = export_calendar([{**event, "date":"2026-12-01"}])
        for physical in original.split(b"\r\n"):
            self.assertLessEqual(len(physical), 75)
            physical.decode("utf-8")
        unfolds = original.replace(b"\r\n ", b"")
        self.assertIn(b"\\; x\\, y\\nBEGIN:VEVENT", unfolds)
        self.assertEqual(unfolds.count(b"\r\nBEGIN:VEVENT\r\n"), 1)
        uid = next(line for line in unfolds.splitlines() if line.startswith(b"UID:"))
        self.assertIn(uid, shifted.replace(b"\r\n ", b""))

    def test_local_appointment_time_and_cancellation(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier",
                        "inbox_store", "project_store", "business_imports"):
                self.addCleanup(getattr(main, key).cache_clear)
            route = "/api/agenda/appointments"
            item = {"title":"Revue","day":"2026-07-10","clock":"14:30","duration":45}
            created = api.post(route, json=item)
            self.assertEqual(created.status_code, 201, created.text)
            key = created.json()["id"]
            day = {"start": "2026-07-10", "days": 1}
            row = api.get("/api/agenda", params=day).json()["items"][0]
            self.assertEqual((row["clock"], row["duration"]), ("14:30", 45))
            data = api.get("/api/agenda/export.ics", params=day).content
            self.assertIn(b"DTSTART:20260710T123000Z", data)
            self.assertIn(b"DTEND:20260710T131500Z", data)
            self.assertEqual(api.post(route, json={**item, "day":"2026-03-29", "clock":"02:30"}).status_code, 422)
            self.assertEqual(api.post(route, json={**item, "day":"2026-10-25", "clock":"02:30"}).status_code, 422)
            api.put(f"{route}/{key}", json={**item, "status":"cancelled"}).raise_for_status()
            self.assertEqual(api.get("/api/agenda", params=day).json()["count"], 0)
            cancelled = api.get("/api/agenda", params={**day,"include_cancelled":"true"}).json()["items"][0]
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertNotIn(b"BEGIN:VEVENT", api.get("/api/agenda/export.ics", params=day).content)

    def test_linked_appointments_flag_overlaps_and_lead_to_agenda(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
        }), TestClient(main.app) as api:
            for key in ("workflow_memory", "wedding_store", "wedding_dossier", "inbox_store",
                        "project_store", "business_imports", "ceo_briefs", "ceo_jobs", "site_operations"):
                self.addCleanup(getattr(main, key).cache_clear)
            project = api.post("/api/projects", json={"title":"Site","owner":"Coordination","status":"active"}).json()["id"]
            day = main.wedding_today().isoformat()
            item = {"title":"Point projet","day":day,"clock":"14:00","duration":30,
                    "target_kind":"project", "target_id":project}
            url = "/api/agenda/appointments"
            first = api.post(url, json=item).json()["id"]
            second = api.post(url, json={**item,"title":"Point voisin","clock":"14:30"}).json()["id"]
            self.assertEqual(api.post(url, json={**item,"target_id":"0"*32}).status_code, 404)
            params = {"start":day,"days":1}
            rows = api.get("/api/agenda", params=params).json()["items"]
            self.assertFalse(any(row["overlap"] for row in rows))
            api.put(url + "/" + second, json={**item,"clock":"14:15"}).raise_for_status()
            rows = api.get("/api/agenda", params=params).json()["items"]
            self.assertTrue(all(row["overlap"] and row["target_id"] == project for row in rows))
            brief = api.post("/api/ceo/brief").json()
            self.assertIn(f"#agenda?date={day}&rdv={first}", [row["link"] for row in brief["items"]])
            api.put(url + "/" + second, json={**item,"clock":"14:15","status":"cancelled"}).raise_for_status()
            self.assertFalse(api.get("/api/agenda", params=params).json()["items"][0]["overlap"])
