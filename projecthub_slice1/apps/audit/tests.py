from io import StringIO
from unittest import skipUnless

from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

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
        # actor is a PROTECT foreign key: Django refuses the delete before any SQL reaches the
        # audit table, so the triggers are never involved and the history stays intact.
        # Accounts with history are deactivated instead of deleted.
        with self.assertRaises(ProtectedError):
            self.actor.delete()
        with self.assertRaises(ProtectedError):
            User.objects.filter(pk=self.actor.pk).delete()

        self.assertTrue(User.objects.filter(pk=self.actor.pk).exists())
        self.event.refresh_from_db()
        self.assertEqual((self.event.actor_id, self.event.summary), (self.actor.pk, "Original summary"))

        self.actor.is_active = False
        self.actor.save(update_fields=["is_active"])
        self.assertEqual(AuditEvent.objects.filter(actor=self.actor).count(), 1)

    def test_purge_demo_leaves_audit_history_untouched(self):
        User.objects.create(username="audit.demo.purge", role=Role.STUDENT, is_demo=True)

        call_command("purge_demo", stdout=StringIO())

        self.assertFalse(User.objects.filter(is_demo=True).exists())
        self._assert_unchanged()
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_audit_page_shows_events_without_an_actor(self):
        # e.g. an assignment made by a management command, with assigned_by=None
        log_event(actor=None, action="test.system", summary="System action")
        self.client.force_login(self.actor)

        response = self.client.get(reverse("audit_log"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System action")
        self.assertContains(response, "the system")


class ReadableAuditLogTests(TestCase):
    """The audit page shows labels and "Field: old -> new", never raw codes or dictionaries."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create(username="readable.admin", first_name="Solomon", last_name="Ejeh", role=Role.ADMIN)

    def _event(self, action, details, summary="Something happened"):
        return log_event(actor=self.admin, action=action, summary=summary, details=details)

    def test_field_changes_read_as_before_and_after(self):
        from .templatetags.audit_display import audit_details

        event = self._event("account.staff_updated", {"department": {"from": "", "to": "Computer Science"},
                                                      "can_assign_supervisors": {"from": "False", "to": "True"},
                                                      "role": {"from": "supervisor", "to": "coordinator"}})

        self.assertEqual(audit_details(event), [
            {"label": "Department", "before": "(blank)", "after": "Computer Science"},
            {"label": "Can assign supervisors", "before": "No", "after": "Yes"},
            {"label": "Role", "before": "Supervisor", "after": "Coordinator"},
        ])

    def test_facts_and_stage_changes(self):
        from .templatetags.audit_display import audit_details

        created = self._event("account.staff_created", {"role": "supervisor", "department": "Computer Science",
                                                        "can_assign_supervisors": False})
        stage = self._event("project.stage_changed", {"from": "2", "to": "3", "note": "Work started."})

        self.assertEqual(audit_details(created), [
            {"label": "Role", "value": "Supervisor"}, {"label": "Department", "value": "Computer Science"},
            {"label": "Can assign supervisors", "value": "No"},
        ])
        self.assertEqual(audit_details(stage), [
            {"label": "Stage", "before": "Approved by the department", "after": "In progress"},
            {"label": "Note", "value": "Work started."},
        ])

    def test_labels_for_known_and_unknown_actions(self):
        from .templatetags.audit_display import audit_label

        self.assertEqual(audit_label("structure.department_updated"), "Department updated")
        self.assertEqual(audit_label("account.password_set"), "Temporary password replaced")
        self.assertEqual(audit_label("something.new_thing"), "Something new thing")

    def test_page_shows_readable_entries(self):
        self._event("account.staff_updated", {"first_name": {"from": "", "to": "Solomon"}}, summary="Updated staff account admin")
        self.client.force_login(self.admin)

        response = self.client.get(reverse("audit_log"))

        self.assertContains(response, "Staff account updated")
        self.assertContains(response, "<dt>First name</dt>", html=False)
        self.assertContains(response, '<span class="audit-after">Solomon</span>', html=False)
        self.assertNotContains(response, "{&#x27;first_name&#x27;")
        self.assertContains(response, "By Solomon Ejeh")
