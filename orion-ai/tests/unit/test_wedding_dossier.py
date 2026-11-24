from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class WeddingDossierTests(TestCase):
    def test_full_dossier_and_reminder(self):
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"ORION_WEDDING_DB": str(Path(directory) / "wedding.db"),
                           "ORION_DB": str(Path(directory) / "orion.db")}
        ):
            self.addCleanup(main.inbox_store.cache_clear)
            self.addCleanup(main.workflow_memory.cache_clear)
            self.addCleanup(main.wedding_dossier.cache_clear)
            self.addCleanup(main.wedding_store.cache_clear)
            with TestClient(main.app) as api:
                plan = api.post("/api/wedding/plans", json={
                    "nom": "Mariage de test", "date_mariage": "2027-06-15",
                })
                self.assertEqual(plan.status_code, 201)
                path = "/api/wedding/plans/" + plan.json()["id"]
                first_task = plan.json()["tasks"][0]
                changed = api.patch(path, json={"date_mariage": "2027-06-16"}).json()
                self.assertEqual(changed["date"], "2027-06-16")
                self.assertNotEqual(changed["tasks"][0]["echeance"], first_task["echeance"])
                due = main.wedding_today().isoformat()

                def save(kind, data, key=None, expected=200):
                    response = api.put(path + "/dossier", json={"kind": kind, "id": key, "data": data})
                    self.assertEqual(response.status_code, expected, response.text)
                    return response.json().get("id")

                save("client", {"name": "Client", "stage": "prospect", "budget": 250_000})
                vendor = save("vendor", {"name": "Traiteur", "email": "test@example.com"})
                quote = save("quote", {"name": "Repas", "vendor": vendor, "amount": 100_000,
                                       "status": "accepted"})
                payment = {"name": "Acompte repas", "quote": quote, "amount": 20_000,
                           "status": "pending", "due": due}
                payment_id = save("payment", payment)
                save("payment", {**payment, "amount": 81_000}, expected=422)
                save("guest", {"name": "Invité", "status": "yes"})
                save("day", {"name": "Accueil", "time": "14:00", "responsible": "Équipe", "status": "pending"})
                save("summary", {"notes": "Bilan du dossier"})

                closed = api.post("/api/wedding/plans", json={
                    "nom": "Mariage clôturé", "date_mariage": "2025-06-15",
                }).json()["id"]
                self.assertEqual(api.put(f"/api/wedding/plans/{closed}/dossier", json={
                    "kind": "client", "data": {"name": "Ancien client", "stage": "closed"},
                }).status_code, 200)
                overview = api.get("/api/wedding/overview").json()
                self.assertEqual(overview["closed"], 1)
                self.assertEqual(len(overview["dossiers"]), 1)
                self.assertEqual(overview["totals"]["drafts"], 0)
                self.assertEqual(overview["totals"]["business_due"], 1)
                for _ in range(2):
                    prepared = api.post("/api/wedding/overview/relances").json()
                    self.assertEqual(prepared["totals"]["drafts"], 1)
                    self.assertEqual(prepared["totals"]["balance"], 100_000)

                for _ in range(2):
                    detected = api.post(path + "/relances").json()
                    self.assertEqual(len(detected["reminders"]), 1)
                    self.assertEqual(detected["committed"], 100_000)
                    self.assertEqual(detected["reminders"][0]["email"], "test@example.com")
                    self.assertEqual(detected["reminders"][0]["status"], "draft")

                def transition(action, result=""):
                    return api.patch(path + "/relances", json={
                        "kind": "payment", "target": payment_id, "due": due,
                        "action": action, "result": result,
                    })

                self.assertEqual(transition("record", "Envoyé").status_code, 422)
                save("vendor", {"name": "Traiteur", "email": "new@example.com"}, vendor)
                self.assertEqual(transition("approve").status_code, 422)
                self.assertEqual(api.post(path + "/relances").status_code, 200)
                self.assertEqual(transition("approve").json()["email"], "new@example.com")
                self.assertEqual(transition("record", "Réception confirmée").status_code, 200)
                save("payment", {**payment, "status": "paid"}, payment_id)
                dossier = api.get(path + "/dossier").json()
                self.assertEqual(dossier["paid"], 20_000)
                self.assertEqual(dossier["records"]["summary"]["summary"]["notes"], "Bilan du dossier")
                self.assertEqual(dossier["reminders"][0]["result"], "Réception confirmée")
                self.assertEqual(dossier["reminders"][0]["status"], "recorded")
                final = api.get("/api/wedding/overview").json()["totals"]
                self.assertEqual(final["balance"], 80_000)
                self.assertEqual(final["drafts"], 0)
                self.assertEqual(final["business_due"], 0)
