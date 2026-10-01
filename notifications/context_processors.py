"""
Makes the poll interval available to base.html.

base.html is rendered by every view in the project, so passing this through
each one individually would mean touching every view to change one number.
A context processor keeps the value in settings.py where it belongs.
"""

from django.conf import settings


def poll_settings(request):
    return {"poll_seconds": settings.NOTIFICATION_POLL_SECONDS}
