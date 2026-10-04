"""
Phase 6 tests: the notification helper, the poll endpoint and the list page.

The triggers themselves are tested in applications/tests.py, next to the
actions that fire them.
"""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import SeekerProfile, User

from . import services
from .models import Notification

PASSWORD = "pw-for-tests-9931"


def make_user(email="seeker@example.com"):
    user = User.objects.create_user(
        email=email, password=PASSWORD, role=User.Role.JOB_SEEKER
    )
    SeekerProfile.objects.create(user=user, full_name="محمد عثمان")
    return user


class NotifyTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_notify_creates_a_row(self):
        notification = services.notify(
            self.user, title="عنوان", body="نص", link="/jobs/1/"
        )
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "عنوان")
        self.assertFalse(notification.is_read)

    def test_body_and_link_are_optional(self):
        notification = services.notify(self.user, title="عنوان فقط")
        self.assertEqual(notification.body, "")
        self.assertEqual(notification.link, "")

    def test_notify_with_no_user_is_a_no_op(self):
        self.assertIsNone(services.notify(None, title="لا أحد"))
        self.assertFalse(Notification.objects.exists())

    def test_a_failure_is_swallowed_rather_than_raised(self):
        """
        A notification must never take down the action that triggered it.

        A title longer than the column allows would raise on a strict backend;
        the caller -- a candidate applying for a job -- has no sensible way to
        handle that, so notify() absorbs it.
        """
        from unittest.mock import patch

        with patch.object(
            Notification.objects, "create", side_effect=Exception("db is down")
        ):
            self.assertIsNone(services.notify(self.user, title="عنوان"))

    def test_unread_count_ignores_read_rows(self):
        services.notify(self.user, title="1")
        services.notify(self.user, title="2")
        Notification.objects.filter(title="1").update(is_read=True)
        self.assertEqual(services.unread_count(self.user), 1)

    def test_unread_count_is_per_user(self):
        other = make_user("other@example.com")
        services.notify(other, title="theirs")
        self.assertEqual(services.unread_count(self.user), 0)
        self.assertEqual(services.unread_count(other), 1)

    def test_newest_notification_comes_first(self):
        services.notify(self.user, title="older")
        services.notify(self.user, title="newer")
        self.assertEqual(
            [n.title for n in Notification.objects.all()], ["newer", "older"]
        )


class EmailTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_send_email_delivers(self):
        self.assertTrue(services.send_email(self.user, "موضوع", "نص الرسالة"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "موضوع")
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_a_user_with_no_email_is_skipped(self):
        self.user.email = ""
        self.assertFalse(services.send_email(self.user, "موضوع", "نص"))
        self.assertEqual(len(mail.outbox), 0)

    def test_a_send_failure_is_swallowed(self):
        from unittest.mock import patch

        with patch("notifications.services.send_mail", side_effect=Exception("smtp down")):
            self.assertFalse(services.send_email(self.user, "موضوع", "نص"))


class PollEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_it_returns_the_unread_count_as_json(self):
        services.notify(self.user, title="1")
        services.notify(self.user, title="2")

        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications:poll"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"unread_count": 2})

    def test_an_anonymous_visitor_gets_zero_not_a_login_page(self):
        """
        login_required would answer a fetch() with HTML, which the script
        cannot parse. Zero is both true and harmless for a visitor.
        """
        response = self.client.get(reverse("notifications:poll"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 0})

    def test_one_user_never_sees_another_users_count(self):
        other = make_user("other@example.com")
        services.notify(other, title="theirs")

        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("notifications:poll")).json()["unread_count"], 0
        )


class NotificationListTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_the_list_shows_this_users_notifications(self):
        services.notify(self.user, title="إشعار خاص بي")
        other = make_user("other@example.com")
        services.notify(other, title="إشعار شخص آخر")

        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إشعار خاص بي")
        self.assertNotContains(response, "إشعار شخص آخر")

    def test_opening_the_list_marks_everything_read(self):
        services.notify(self.user, title="غير مقروء")
        self.client.get(reverse("notifications:list"))
        self.assertEqual(services.unread_count(self.user), 0)

    def test_the_visit_that_marks_them_read_still_highlights_them(self):
        """
        Marking happens after the queryset is captured, so the user can see
        what was new on the visit that cleared the badge.
        """
        notification = services.notify(self.user, title="جديد")
        response = self.client.get(reverse("notifications:list"))
        self.assertIn(notification.pk, response.context["unread_ids"])

        # On the next visit it is no longer highlighted.
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.context["unread_ids"], set())

    def test_an_anonymous_visitor_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_the_badge_and_polling_script_appear_for_a_logged_in_user(self):
        response = self.client.get(reverse("notifications:list"))
        content = response.content.decode()
        self.assertIn('id="notification-count"', content)
        self.assertIn("visibilityState", content)

    def test_the_polling_script_is_not_served_to_anonymous_visitors(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:home"))
        self.assertNotIn('id="notification-count"', response.content.decode())
