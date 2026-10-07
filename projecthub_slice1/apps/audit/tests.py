from unittest import skipUnless

from django.db import DatabaseError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.accounts.models import Role, User

from .models import AuditEvent
from .services import log_event

TRIGGER_VENDORS = ("sqlite", "mysql")
TABLE = connection.ops.quote_name(AuditEvent._meta.db_table)


def _trigger_names():
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = %s",
                [AuditEvent._meta.db_table],
            )
        else:
            cursor.execute(
                "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = %s",
                [AuditEvent._meta.db_table],
            )
        return {row[0] for row in cursor.fetchall()}


class AuditAppendOnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create(username="audit.admin", role=Role.ADMIN)
        cls.event = log_event(actor=cls.actor, action="test.recorded", summary="Original summary")

    def _raw(self, sql, params=()):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)

    def _assert_unchanged(self):
        self.event.refresh_from_db()
        self.assertEqual(self.event.summary, "Original summary")

    def test_events_can_still_be_added(self):
        log_event(actor=self.actor, action="test.second", summary="Second")

        self.assertEqual(AuditEvent.objects.count(), 2)

    def test_demo_activity_is_still_not_logged(self):
        demo_user = User.objects.create(username="audit.demo", role=Role.STUDENT, is_demo=True)

        self.assertIsNone(log_event(actor=demo_user, action="test.demo", summary="Demo"))
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_python_guards_refuse_changes(self):
        self.event.summary = "Rewritten"
        with self.assertRaises(PermissionError):
            self.event.save()
        with self.assertRaises(PermissionError):
            self.event.delete()
        with self.assertRaises(PermissionError):
            AuditEvent.objects.filter(pk=self.event.pk).update(summary="Rewritten")
        with self.assertRaises(PermissionError):
            AuditEvent.objects.all().delete()
        self._assert_unchanged()

    @skipUnless(connection.vendor in TRIGGER_VENDORS, "audit triggers exist only on SQLite and MySQL")
    def test_triggers_are_installed(self):
        self.assertEqual(_trigger_names(), {"audit_event_no_update", "audit_event_no_delete"})

    @skipUnless(connection.vendor in TRIGGER_VENDORS, "audit triggers exist only on SQLite and MySQL")
    def test_raw_sql_update_is_refused_by_the_database(self):
        with self.assertRaisesMessage(DatabaseError, "audit log is append-only"):
            self._raw(f"UPDATE {TABLE} SET summary = %s WHERE id = %s", ["Rewritten", self.event.pk])
        self._assert_unchanged()

    @skipUnless(connection.vendor in TRIGGER_VENDORS, "audit triggers exist only on SQLite and MySQL")
    def test_raw_sql_delete_is_refused_by_the_database(self):
        with self.assertRaisesMessage(DatabaseError, "audit log is append-only"):
            self._raw(f"DELETE FROM {TABLE} WHERE id = %s", [self.event.pk])
        with self.assertRaisesMessage(DatabaseError, "audit log is append-only"):
            self._raw(f"DELETE FROM {TABLE}")
        self.assertTrue(AuditEvent.objects.filter(pk=self.event.pk).exists())

    def test_user_with_audit_history_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.actor.delete()
        self.assertTrue(AuditEvent.objects.filter(actor=self.actor).exists())
