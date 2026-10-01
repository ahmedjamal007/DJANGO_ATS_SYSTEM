from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CompanyProfile, SeekerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Rebuilt fieldsets: the stock UserAdmin refers to `username`, which this
    project's user model does not have.
    """

    ordering = ["email"]
    list_display = ["email", "role", "is_staff", "is_active"]
    list_filter = ["role", "is_staff", "is_active"]
    search_fields = ["email"]

    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Personal info", {"fields": ["first_name", "last_name"]}),
        ("Role", {"fields": ["role"]}),
        (
            "Permissions",
            {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]},
        ),
        ("Important dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "role", "password1", "password2"],
            },
        ),
    ]


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "location"]
    search_fields = ["name"]


@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "location"]
    search_fields = ["full_name"]
