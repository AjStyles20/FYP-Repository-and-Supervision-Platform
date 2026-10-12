"""Every in-app alert is also emailed once to the recipient's Baze email."""

from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from apps.accounts.models import Role, User

from .models import Notification, NotificationKind
from .services import notify


@override_settings(EMAIL_ALERTS=True, SITE_URL="https://projecthub.bazeuniversity.edu.ng")
class AlertEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create(username="ada@bazeuniversity.edu.ng", email="ada@bazeuniversity.edu.ng",
                                          first_name="Ada", role=Role.STUDENT)

    def send(self, recipient=None):
        with self.captureOnCommitCallbacks(execute=True):
            return notify(recipient or self.student, NotificationKind.AT_RISK_PROJECT, self.student,
                          title="Your project needs attention", body="No meeting in 3 weeks.", url="/projects/my-project/")

    def test_an_alert_is_emailed_once_with_a_link(self):
        self.send()
        self.send()  # the same alert within 24 hours is skipped, and so is its email
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (["ada@bazeuniversity.edu.ng"], "Your project needs attention"))
        self.assertIn("No meeting in 3 weeks.", message.body)
        self.assertIn("https://projecthub.bazeuniversity.edu.ng/projects/my-project/", message.body)

    def test_no_email_for_demo_accounts_accounts_without_email_or_when_switched_off(self):
        demo = User.objects.create(username="demo.x", email="x@bazeuniversity.edu.ng", role=Role.STUDENT, is_demo=True)
        no_email = User.objects.create(username="noemail", role=Role.STUDENT)
        self.send(demo)
        self.send(no_email)
        with override_settings(EMAIL_ALERTS=False):
            self.send()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Notification.objects.count(), 3)  # the in-app alerts are still there

    def test_a_mail_failure_keeps_the_alert(self):
        with mock.patch("apps.supervision.services.send_mail", side_effect=OSError("mail server down")), \
                self.assertLogs("apps.supervision.services", level="WARNING"):
            self.send()
        self.assertTrue(Notification.objects.filter(recipient=self.student).exists())
