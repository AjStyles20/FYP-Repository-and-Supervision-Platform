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


class RegistrationStatusExplainerTests(SimpleTestCase):
    def test_has_the_required_sections_and_five_questions(self):
        text = (DOCS / "explain" / "registration-status.md").read_text(encoding="utf-8")
        for heading in ("## Purpose", "## Files involved", "## Flow", "## Rules", "## Self-test"):
            self.assertIn(heading, text)
        questions = text.split("## Self-test", 1)[1].split("<details>", 1)[0]
        self.assertEqual(len(re.findall(r"^\d\. ", questions, re.M)), 5)

    def test_every_code_name_it_mentions_exists(self):
        source = (settings.BASE_DIR / "apps" / "accounts" / "views.py").read_text(encoding="utf-8")
        for name in ("def registration_status", "def registration_status_token", "def _registration_for_token", "def _rejection_reason"):
            self.assertIn(name, source)
        for path in ("templates/registration/status.html", "static/js/poll.js", "static/js/registration-status.js"):
            self.assertTrue((settings.BASE_DIR / path).is_file(), path)
