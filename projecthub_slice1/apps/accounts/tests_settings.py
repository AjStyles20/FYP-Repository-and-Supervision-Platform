"""The database choice: SQLite never borrows the MySQL database name (that left stray files behind)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.settings import database_settings


class DatabaseSettingsTests(SimpleTestCase):
    def test_sqlite_ignores_the_mysql_db_name(self):
        name = database_settings({"DB_ENGINE": "sqlite", "DB_NAME": "baze_projecthub"})["default"]["NAME"]
        self.assertEqual(Path(name), settings.BASE_DIR / "db.sqlite3")

    def test_sqlite_path_is_absolute_even_when_given_relative(self):
        relative = database_settings({"DB_ENGINE": "sqlite", "SQLITE_PATH": "demo.sqlite3"})["default"]["NAME"]
        self.assertEqual(Path(relative), settings.BASE_DIR / "demo.sqlite3")
        absolute = settings.BASE_DIR.parent / "elsewhere.sqlite3"
        chosen = database_settings({"DB_ENGINE": "sqlite", "SQLITE_PATH": str(absolute)})["default"]["NAME"]
        self.assertEqual(Path(chosen), absolute)

    def test_mysql_still_uses_db_name(self):
        default = database_settings({"DB_NAME": "baze_projecthub"})["default"]
        self.assertEqual((default["ENGINE"], default["NAME"]), ("django.db.backends.mysql", "baze_projecthub"))
