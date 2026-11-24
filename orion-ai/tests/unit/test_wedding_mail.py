from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class WeddingMailTests(TestCase):
    def test_approval_delivery_and_duplicate_protection(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "ORION_DB": str(Path(tmp) / "orion.db"), "ORION_WEDDING_DB": str(Path(tmp) / "wedding.db"),
            "ORION_SMTP_HOST": "smtp.example.com", "ORION_SMTP_FROM": "orion@example.com",
            "ORION_SMTP_USER": "", "ORION_SMTP_PASSWORD": "",
        }), TestClient(main.app) as api:
            for name in ("workflow_memory", "wedding_store", "wedding_dossier", "inbox_store"):
                self.addCleanup(getattr(main, name).cache_clear)
            plan = api.post("/api/wedding/plans", json={"nom": "Test", "date_mariage": "2027-07-01"}).json()
            path = f"/api/wedding/plans/{plan['id']}"
            day = main.wedding_today().isoformat()
            guest = {"name": "Invité", "email": "client@example.com", "status": "pending", "due": day}
            item = api.put(path + "/dossier", json={"kind": "guest", "data": guest}).json()["id"]
            api.post(path + "/relances").raise_for_status()
            identity = {"kind": "guest", "target": item, "due": day}
            endpoint = path + "/relances/mail"
            body = {**identity, "confirm": True}
            with patch.object(main, "send_reminder", return_value=("accepted", "SMTP accepté")) as smtp:
                self.assertEqual(api.post(endpoint, json=body).status_code, 422)
                api.patch(path + "/relances", json={**identity, "action": "approve"}).raise_for_status()
                sent_result = api.post(endpoint, json=body)
                self.assertEqual(sent_result.json()["status"], "sent")
                self.assertEqual(api.post(endpoint, json=body).status_code, 422)
                smtp.assert_called_once()
            saved = api.patch(path + "/relances", json={**identity, "action": "record", "result": "Réponse reçue"}).json()
            self.assertEqual(saved["status"], "recorded")
            self.assertEqual(saved["mail_outcome"], "accepted")

            another = api.put(path + "/dossier", json={"kind": "guest", "data": guest}).json()["id"]
            uncertain = {**identity, "target": another}
            api.post(path + "/relances").raise_for_status()
            api.patch(path + "/relances", json={**uncertain, "action": "approve"}).raise_for_status()
            with patch.object(main, "send_reminder", return_value=("unknown", "Accusé absent")) as smtp:
                self.assertEqual(api.post(endpoint, json={**uncertain, "confirm": True}).json()["status"], "unknown")
                self.assertEqual(api.post(endpoint, json={**uncertain, "confirm": True}).status_code, 422)
                smtp.assert_called_once()
