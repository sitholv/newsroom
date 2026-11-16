"""Trusted administration of accounts, publisher membership and audit
records."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    ApprovalDelivery,
    ApprovalLog,
    Article,
    Newsletter,
    Publisher,
    User,
)


@admin.register(User)
class NewsUserAdmin(UserAdmin):
    """Let trusted administrators assign the otherwise unavailable
    editor role."""

    fieldsets = UserAdmin.fieldsets + (
        ("Editorial role", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Editorial identity", {"fields": ("email", "role")}),
    )
    list_display = ["username", "email", "role", "is_active", "is_staff"]


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    """Maintain role-filtered journalist and editor memberships."""

    list_display = ["name"]
    filter_horizontal = ["journalists", "editors"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Keep approval in the audited application workflow, not a raw
    checkbox."""

    list_display = ["title", "author", "publisher", "approved"]
    readonly_fields = ["approved", "created_at"]


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Offer only approved articles when maintaining newsletter
    contents."""

    list_display = ["title", "author", "created_at"]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Never insert a private draft into a public newsletter through
        admin."""
        if db_field.name == "articles":
            kwargs["queryset"] = Article.objects.filter(approved=True)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(ApprovalDelivery, ApprovalLog)
class AuditAdmin(admin.ModelAdmin):
    """Expose publication audit rows without allowing manual forgery."""

    def has_add_permission(self, request):
        """Audit records are created only by the publication
        services."""
        return False

    def has_change_permission(self, request, obj=None):
        """Keep audit flags immutable through the administration
        site."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Preserve delivery history while its article exists."""
        return False
