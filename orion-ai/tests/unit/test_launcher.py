import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from lancer_orion import database_problem, diagnostics


class LauncherTests(TestCase):
    def test_occupied_port_and_corrupt_database_are_reported(self):
        with TemporaryDirectory() as tmp, socket.socket() as listener:
            path = Path(tmp) / "orion.sqlite3"
            path.write_text("not a database")
            self.assertIsNotNone(database_problem(path))
            self.assertIsNone(database_problem(Path(tmp) / "new" / "sqlite.db"))
            listener.bind(("127.0.0.1", 0))
            with patch.dict("os.environ", {"ORION_DB":str(path)}):
                issues = diagnostics(listener.getsockname()[1])
            self.assertTrue(any("ne peut pas être utilisé" in issue for issue in issues))
            self.assertTrue(any("base inaccessible" in issue for issue in issues))
