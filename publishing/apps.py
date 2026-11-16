"""Configure role permissions once Django has migrated the database."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def configure_roles(sender, **kwargs):
    """Assign only the editorial model permissions required by each
    role."""
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    # Create permissions first, regardless of application ordering.
    create_permissions(
        sender, verbosity=0, using=kwargs.get("using", "default")
    )
    assignments = {
        "reader": ["view_article", "view_newsletter", "view_publisher"],
        "journalist": [
            "view_article",
            "add_article",
            "change_article",
            "delete_article",
            "view_newsletter",
            "add_newsletter",
            "change_newsletter",
            "delete_newsletter",
            "view_publisher",
        ],
        "editor": [
            "view_article",
            "change_article",
            "delete_article",
            "approve_article",
            "view_newsletter",
            "add_newsletter",
            "change_newsletter",
            "delete_newsletter",
            "view_publisher",
        ],
    }
    for name, codenames in assignments.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="publishing",
                codename__in=codenames,
            )
        )


class PublishingConfig(AppConfig):
    """Install the idempotent role-configuration migration hook."""

    name = "publishing"

    def ready(self):
        """Connect after all app models are available, without querying
        here."""
        post_migrate.connect(
            configure_roles,
            sender=self,
            dispatch_uid="publishing.configure_roles",
        )
