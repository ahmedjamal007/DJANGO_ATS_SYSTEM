"""
Two views: a JSON endpoint the navbar polls, and the list page.

There is no dropdown. A plain page is simpler, works without JavaScript, and
is one less thing to get wrong on a right-to-left layout.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from . import services
from .models import Notification


def poll(request):
    """
    Return the unread count as JSON.

    Not decorated with login_required: that would answer a fetch() with an
    HTML login page, which the caller cannot parse. An anonymous visitor has
    no notifications, so zero is both true and harmless.
    """
    return JsonResponse({"unread_count": services.unread_count(request.user)})


@login_required
def notification_list(request):
    """
    The full list, newest first.

    Everything unread is marked read on the way out, but the ids are captured
    *before* that so this render can still highlight what was new. Marking
    after rendering is what stops a visit from quietly erasing the only
    signal the user came here for.
    """
    notifications = list(Notification.objects.filter(user=request.user)[:100])
    unread_ids = {n.pk for n in notifications if not n.is_read}

    if unread_ids:
        Notification.objects.filter(pk__in=unread_ids).update(is_read=True)

    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications, "unread_ids": unread_ids},
    )
