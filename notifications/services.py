"""
Creating notifications.

Every notification in the project goes through `notify()`. Keeping one
entry point means the triggers are findable -- grep for `notify(` and you
have the complete list of things this system tells people about.

Both functions here are deliberately forgiving. A notification is a side
effect of something more important: a candidate applying, a recruiter moving
someone forward. If writing the notification fails, the thing that actually
mattered must still succeed, so failures are logged and swallowed rather than
raised into a caller that has no sensible way to handle them.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


def notify(user, title, body="", link=""):
    """
    Create one in-app notification.

    Returns the Notification, or None when it could not be created. Callers
    are not expected to check -- the return value is there for tests.
    """
    if user is None:
        return None

    try:
        return Notification.objects.create(
            user=user, title=title, body=body, link=link
        )
    except Exception:
        # Never let a notification take down the action that triggered it.
        logger.exception("Could not create notification for user %s", getattr(user, "pk", None))
        return None


def send_email(user, subject, message):
    """
    Send one email through whatever backend is configured.

    In development that is the console backend, so mail appears in the
    runserver output rather than being sent. Wrapped for the same reason as
    notify(): a mail server being down must not roll back a stage change.
    """
    if user is None or not user.email:
        return False

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Could not send email to %s", user.email)
        return False


def unread_count(user):
    """How many unread notifications this user has. Used by the poll endpoint."""
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()
