"""
In-app notifications.

One row per message per user. There is no fan-out or grouping: at this scale
a notification is cheap, and a simple table is far easier to reason about
than anything cleverer.
"""

from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="المستخدم",
    )
    title = models.CharField("العنوان", max_length=200)
    body = models.TextField("النص", blank=True)
    # A relative path inside this site, so the list page can link straight to
    # whatever the notification is about.
    link = models.CharField("الرابط", max_length=300, blank=True)
    is_read = models.BooleanField("مقروءة", default=False)
    created_at = models.DateTimeField("التاريخ", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The poll endpoint runs this exact filter every 20 seconds per
            # logged-in user, so it gets an index rather than a table scan.
            models.Index(fields=["user", "is_read"], name="notif_user_unread_idx"),
        ]
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"

    def __str__(self):
        return f"{self.user_id}: {self.title}"
