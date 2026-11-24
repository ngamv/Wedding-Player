import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from scripts.orion_backup import backup, restore


class LocalOperationsTests(TestCase):
    def test_backup_restore_and_failure_journal(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("brief_journal", "inbox_store", "workflow_memory", "wedding_dossier", "wedding_store"):
                self.addCleanup(getattr(main, name).cache_clear)
            with patch.dict("os.environ", {
                "ORION_DB": str(directory / "source.db"),
                "ORION_WEDDING_DB": str(directory / "events.db"),
            }), TestClient(main.app) as api:
                api.post("/api/wedding/plans", json={"nom": "Mariage restauration", "date_mariage": "2027-07-01"}).raise_for_status()
                with patch.object(main.WeddingDossier, "overview", side_effect=ValueError("incident simulé")):
                    self.assertEqual(api.post("/api/wedding/brief?source=n8n").status_code, 422)
                self.assertEqual(main.brief_journal().latest()[0]["state"], "failed")
                api.post("/api/wedding/brief").raise_for_status()
                archive = directory / "backup.zip"
                backup(archive)
                recovered = directory / "recovered"
                restore(archive, recovered)
                with self.assertRaises(FileExistsError):
                    restore(archive, recovered)
                with closing(sqlite3.connect(recovered / "orion.sqlite3")) as db:
                    self.assertEqual(db.execute("SELECT state FROM wedding_brief_runs ORDER BY id").fetchall(),
                                     [("failed",), ("completed",)])
                with closing(sqlite3.connect(recovered / "wedding.sqlite3")) as db:
                    self.assertEqual(db.execute("SELECT nom FROM wedding_plans").fetchone()[0], "Mariage restauration")
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM wedding_briefs").fetchone()[0], 1)

    def test_daily_archive_is_verified_and_last_success_survives_failure(self):
        from scripts.orion_backup import backup_status, daily_backup, verify

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            orion, wedding = directory / "orion-db", directory / "wedding-db"
            for path in (orion, wedding):
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute("CREATE TABLE example(id INTEGER)")
            settings = {"ORION_DB":str(orion), "ORION_WEDDING_DB":str(wedding),
                        "ORION_BACKUP_DIR": str(directory / "backups")}
            with patch.dict("os.environ", settings):
                snapshot = daily_backup()
                verify(snapshot)
                self.assertEqual(backup_status()["state"], "verified")
                wedding.unlink()
                with self.assertRaises(sqlite3.Error):
                    daily_backup()
                self.assertEqual(backup_status()["state"], "failed")
                self.assertEqual(backup_status()["verified"]["archive"], snapshot.name)
                snapshot.unlink()
                self.assertEqual(backup_status()["state"], "missing")

    def test_manifest_detects_valid_sqlite_replacement_and_accepts_legacy_archive(self):
        import json
        from zipfile import ZipFile
        from scripts.orion_backup import verify

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            orion = directory / "orion.sqlite3"
            wedding = directory / "wedding.sqlite3"
            with closing(sqlite3.connect(orion)) as db, db:
                db.execute("CREATE TABLE projects(id INTEGER)")
                db.execute("INSERT INTO projects VALUES (1)")
            with closing(sqlite3.connect(wedding)) as db, db:
                db.execute("CREATE TABLE wedding_plans(id INTEGER)")
            settings = {"ORION_DB":str(orion), "ORION_WEDDING_DB":str(wedding)}
            archive = directory / "checked.zip"
            with patch.dict("os.environ", settings):
                backup(archive)
            summary = verify(archive)
            self.assertTrue(summary["manifest_verified"])
            self.assertEqual(summary["files"][orion.name]["tables"], {"projects":1})
            with ZipFile(archive) as original:
                manifest = json.loads(original.read("manifest.json"))
            with closing(sqlite3.connect(orion)) as db, db:
                db.execute("INSERT INTO projects VALUES (2)")
            modified = directory / "modified.zip"
            with ZipFile(modified,"w") as bundle:
                for path in (orion, wedding):
                    bundle.write(path, path.name)
                bundle.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Empreinte"):
                restore(modified, directory / "restore")
            self.assertFalse((directory / "restore").exists())
            legacy = directory / "legacy.zip"
            with ZipFile(legacy,"w") as bundle:
                for path in (orion, wedding):
                    bundle.write(path, path.name)
            self.assertFalse(verify(legacy)["manifest_verified"])
            restore(legacy, directory / "restore")

    def test_guided_restore_is_isolated_and_can_be_cancelled(self):
        from scripts.orion_recovery import prepare, recovery_environment

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            orion, wedding = directory / "orion.db", directory / "wedding.db"
            for path in (orion, wedding):
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute("CREATE TABLE example(id INTEGER)")
            settings = {"ORION_DB":str(orion), "ORION_WEDDING_DB":str(wedding),
                        "ORION_SMTP_HOST":"example.test", "ORION_MODE":"ollama"}
            with patch.dict("os.environ", settings):
                archive = directory / "backup.zip"
                backup(archive)
                target = directory / "restores"
                self.assertIsNone(prepare(archive, target, lambda _: False))
                self.assertFalse(target.exists())
                data = prepare(archive, target, lambda report: "SHA-256" in report)
                self.assertIsNotNone(data)
                env = recovery_environment(data)
                self.assertNotIn("ORION_SMTP_HOST", env)
                self.assertEqual(env["ORION_MODE"], "simulation")
                self.assertEqual(Path(env["ORION_DB"]).parent, data)
                with closing(sqlite3.connect(env["ORION_DB"])) as db, db:
                    db.execute("INSERT INTO example VALUES (1)")
                with closing(sqlite3.connect(orion)) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM example").fetchone()[0], 0)

    def test_readiness_distinguishes_ocr_and_smtp_configuration(self):
        from subprocess import CompletedProcess
        from core.local_operations import capability_report

        health = {"mode": "simulation", "services": {
            "Ollama": {"state":"online"}, "n8n": {"state":"error"},
        }}
        environment = {"ORION_OCR_LANG":"fra+eng", "ORION_RECOVERY":"0", "ORION_WHISPER_MODEL":"",
                       "ORION_SMTP_HOST":"smtp.example.test", "ORION_SMTP_FROM":"orion@example.test",
                       "ORION_SMTP_USER":"login-test", "ORION_SMTP_PASSWORD":"secret-test"}
        with patch.dict("os.environ", environment), patch("core.local_operations.shutil.which",
            side_effect=lambda name: None if name == "whisper-cli" else f"/bin/{name}"
        ), patch("core.local_operations.subprocess.run",
                 return_value=CompletedProcess([], 0, "List of available languages:\neng\n", "")):
            report = capability_report(health)
            self.assertEqual(report["PDF texte"]["state"], "ready")
            self.assertEqual(report["JPEG OCR"]["detail"], "Langues OCR manquantes : fra")
            self.assertEqual(report["Transcription audio"]["state"], "action")
            self.assertEqual(report["Relances e-mail"]["state"], "check")
            self.assertNotIn("secret-test", str(report))
            self.assertEqual(report["Réponses IA"]["state"], "action")
