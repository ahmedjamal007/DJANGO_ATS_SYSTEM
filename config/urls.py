from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("jobs/", include("jobs.urls")),
    path("notifications/", include("notifications.urls")),
    path("", include("applications.urls")),
    path("", include("accounts.urls")),
]

# Uploaded files are served by Django in development only. Under DEBUG=0 this
# is a no-op and a real web server takes over.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
