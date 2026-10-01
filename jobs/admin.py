from django.contrib import admin

from .models import Job, SavedJob


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "location", "employment_type", "status", "created_at"]
    list_filter = ["status", "employment_type", "created_at"]
    search_fields = ["title", "description", "company__name"]
    list_select_related = ["company"]
    # Embeddings are machine-written JSON. Showing them in the form would be
    # thousands of unreadable digits.
    exclude = ["description_embedding", "skills_embedding"]


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display = ["seeker", "job", "created_at"]
    list_select_related = ["seeker", "job"]
