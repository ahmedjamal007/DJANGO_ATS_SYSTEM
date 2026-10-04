from django.contrib import admin

from .models import Application, RecruiterNote, Resume, StageHistory


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "seeker", "parse_status", "is_active", "uploaded_at"]
    list_filter = ["parse_status", "is_active", "uploaded_at"]
    search_fields = ["original_filename", "seeker__full_name"]
    list_select_related = ["seeker"]
    readonly_fields = ["parsed_text", "parse_error", "uploaded_at"]
    # Machine-written JSON; thousands of unreadable digits in a form field.
    exclude = ["doc_embedding", "chunk_embeddings"]


class StageHistoryInline(admin.TabularInline):
    model = StageHistory
    extra = 0
    readonly_fields = ["from_stage", "to_stage", "changed_by", "note", "created_at"]


class RecruiterNoteInline(admin.TabularInline):
    model = RecruiterNote
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["seeker", "job", "stage", "match_score", "applied_at"]
    list_filter = ["stage", "applied_at"]
    search_fields = ["seeker__full_name", "job__title"]
    list_select_related = ["seeker", "job"]
    readonly_fields = ["match_score", "semantic_score", "coverage_score", "skill_results"]
    inlines = [StageHistoryInline, RecruiterNoteInline]
