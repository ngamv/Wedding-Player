from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.business_imports import BusinessImports
from core.support import Support


class SupportTests(TestCase):
    def test_status_survives_reimport_and_new_source_status_is_logged(self):
        with TemporaryDirectory() as tmp:
            business = BusinessImports(Path(tmp) / "orion.db")
            support = Support(business)
            csv = "id,title,date,status\nT-1,Demande,2026-11-24,urgent"
            business.import_csv("tickets", csv)
            self.assertEqual(support.list("active", 5, 0)["items"][0]["id"], "T-1")
            support.update("T-1", "closed", "Réponse apportée", "Admin")
            business.import_csv("tickets", csv)
            self.assertEqual(support.get("T-1")["status"], "closed")
            today = date(2026, 11, 24)
            self.assertEqual(business.summary(today, today)[0]["tickets"], 0)
            business.import_csv("tickets", csv.replace("urgent", "open"))
            ticket = support.get("T-1")
            self.assertEqual(ticket["status"], "open")
            self.assertEqual([event["actor"] for event in ticket["history"]], ["Import CSV", "Admin"])
            created = support.create("Question locale", today.isoformat(), "open", "Contexte", "Admin")
            self.assertTrue(created["id"].startswith("orion-"))
