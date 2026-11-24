from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.wedding_checklist import OPTIONS, WeddingChecklist, generer


class WeddingChecklistTests(unittest.TestCase):
    date = date(2027, 6, 12)

    def test_dates_and_options(self):
        all_tasks = {task["id"]: task for task in generer(self.date, OPTIONS)}
        base = {task["id"]: task for task in generer(self.date)}
        self.assertEqual(len(all_tasks), 100)
        self.assertEqual(sum(len(t["dependances"]) for t in all_tasks.values()), 53)
        self.assertEqual(all_tasks[90]["echeance"], "2027-06-12")
        self.assertEqual(all_tasks[100]["echeance"], "2027-08-11")
        self.assertNotIn(52, base)
        self.assertNotIn(61, base)
        self.assertNotIn(52, base[54]["dependances"])

    def test_dependencies_and_persistence(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "wedding.sqlite3"
            store = WeddingChecklist(path)
            plan = store.create("Dossier test", self.date, [])
            ident = plan["id"]
            with self.assertRaises(ValueError):
                store.complete(ident, 6, True)
            for task in (1, 3, 5, 6):
                store.complete(ident, task, True)
            with self.assertRaises(ValueError):
                store.complete(ident, 1, False)
            restored = WeddingChecklist(path)
            self.assertEqual(restored.list()[0]["id"], ident)
            self.assertTrue(restored.get(ident)["tasks"][0]["terminee"])
            due = restored.digest(ident, self.date)
            self.assertNotIn(1, {t["id"] for t in due["en_retard"]})
            self.assertIn(90, {t["id"] for t in due["a_venir"]})
