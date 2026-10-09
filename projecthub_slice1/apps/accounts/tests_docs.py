"""Docs that point into the code must stay true: every code-map row names a real file and name."""

import re

from django.conf import settings
from django.test import SimpleTestCase

DOCS = settings.BASE_DIR.parent / "docs"


class CodeMapTests(SimpleTestCase):
    def test_every_row_points_at_an_existing_name(self):
        rows = [line for line in (DOCS / "code_map.md").read_text(encoding="utf-8").splitlines()
                if line.startswith("| ") and "`" in line]
        self.assertGreaterEqual(len(rows), 25)
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            path = settings.BASE_DIR / re.search(r"`([^`]+)`", cells[1]).group(1)
            name = re.search(r"`([^`]+)`", cells[2]).group(1)
            with self.subTest(row=cells[0]):
                self.assertTrue(path.is_file(), f"{path} does not exist")
                self.assertIn(name, path.read_text(encoding="utf-8"), f"{name} not found in {path}")

    def test_no_line_numbers(self):
        text = (DOCS / "code_map.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\.(py|html|js|css):\d+", text))
