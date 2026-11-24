from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.business_imports import BusinessImports


class BusinessImportsTests(TestCase):
    def test_upsert_totals_and_atomic_rejection(self):
        with TemporaryDirectory() as tmp:
            store = BusinessImports(Path(tmp) / "business.db")
            today = date(2026, 11, 24)
            sales = "id;title;date;status;amount_eur\n1;Facture A;2026-11-24;paid;120,50"
            self.assertEqual(store.import_csv("receipts", sales)["count"], 1)
            store.import_csv("receipts", sales)
            store.import_csv("tickets", "id,title,date,status\nA,Demande urgente,2026-11-24,urgent")
            with self.assertRaisesRegex(ValueError, "Ligne 3"):
                store.import_csv("receipts", sales.replace("120,50", "125,00") + "\n2;Erreur;2026-11-24;paid;abc")
            totals, queue = store.summary(today, today + timedelta(days=7))
            self.assertEqual(totals["receipts"], 12050)
            self.assertEqual(totals["tickets"], 1)
            self.assertEqual(queue[0]["status"], "urgent")
            self.assertEqual(store.latest()["receipts"]["state"], "error")
            self.assertTrue(store.latest()["receipts"]["last_success"])

    def test_sync_folder_skips_replays_and_recovers_from_invalid_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = BusinessImports(root / "business.db")
            file = root / "prospects.csv"
            file.write_text("id;title;date;status\n1;Ancien;2026-11-24;new", encoding="utf-8")
            self.assertEqual(store.sync_folder(root)["prospects.csv"]["count"], 1)
            self.assertTrue(store.sync_folder(root)["prospects.csv"]["unchanged"])

            file.write_text("id;title;date;status\n1;Invalide;2026-11-24;unknown", encoding="utf-8")
            self.assertEqual(store.sync_folder(root)["prospects.csv"]["state"], "error")
            self.assertTrue(store.sync_folder(root)["prospects.csv"]["unchanged"])
            today = date(2026, 11, 24)
            self.assertEqual(store.summary(today, today)[1][0]["title"], "Ancien")

            file.write_text("id;title;date;status\n1;Corrigé;2026-11-24;contacted", encoding="utf-8")
            self.assertEqual(store.sync_folder(root)["prospects.csv"]["state"], "ok")
            self.assertEqual(store.summary(today, today)[0]["prospects"], 0)
            file.unlink()
            self.assertEqual(store.sync_folder(root)["prospects.csv"]["state"], "error")

    def test_finance_windows_and_status_filter(self):
        with TemporaryDirectory() as tmp:
            store = BusinessImports(Path(tmp) / "business.db")
            store.import_csv("receipts", "\n".join([
                "id;title;date;status;amount_eur",
                "1;Encaissé;2026-11-24;paid;125,35",
                "2;À recevoir;2026-11-10;pending;30",
                "3;Annulé;2026-11-10;cancelled;50",
                "4;Ancien;2026-10-25;paid;40",
                "5;Futur;2026-11-25;paid;100",
            ]))
            report = store.finances(date(2026, 11, 24), 30, "pending", 20, 0)
            self.assertEqual(report["start"], "2026-10-26")
            self.assertEqual(report["metrics"], {
                "records": 3, "paid": 12535, "pending": 3000, "previous_paid": 4000,
            })
            self.assertEqual([row["id"] for row in report["items"]], ["2"])
            self.assertIsNotNone(report["source"]["last_success"])
