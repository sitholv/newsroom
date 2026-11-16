"""Normalised editorial records, role relationships and delivery audit
state."""

from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.db import models, transaction


class User(AbstractUser):
    """An account with a unique email and one reader/editorial role.

    save synchronises the managed role group and clears relations that
    no longer fit that role. Subscriptions use normal many-to-many
    relations; public properties return None when they do not apply.
    Passwords use AbstractUser's normal hashing and validation workflow.
    """

    class Role(models.TextChoices):
        """Define the roles used by signup and managed auth groups."""

        READER = "reader", "Reader"
        JOURNALIST = "journalist", "Journalist"
        EDITOR = "editor", "Editor"

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.READER
    )
    followed_publishers = models.ManyToManyField(
        "Publisher", blank=True, related_name="subscribers"
    )
    followed_journalists = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="followers",
        limit_choices_to={"role": "journalist"},
    )

    def save(self, *args, **kwargs):
        """Synchronise managed groups and clear inapplicable
        subscriptions."""
        with transaction.atomic():
            super().save(*args, **kwargs)
            managed = Group.objects.filter(name__in=self.Role.values)
            self.groups.remove(*managed)
            group, _ = Group.objects.get_or_create(name=self.role)
            self.groups.add(group)
            if self.role != self.Role.READER:
                self.followed_publishers.clear()
                self.followed_journalists.clear()
            if self.role != self.Role.JOURNALIST:
                # Role changes must remove follows to a non-author.
                self.followers.clear()
                self.journalist_publishers.clear()
            if self.role != self.Role.EDITOR:
                self.editor_publishers.clear()

    @property
    def publisher_subscriptions(self):
        """Expose reader-only subscriptions, or None for editorial
        accounts."""
        return (
            self.followed_publishers if self.role == self.Role.READER else None
        )

    @property
    def journalist_subscriptions(self):
        """Expose reader-only author subscriptions, otherwise None."""
        return (
            self.followed_journalists
            if self.role == self.Role.READER
            else None
        )

    @property
    def independent_articles(self):
        """Return a journalist's independently published work, otherwise
        None."""
        if self.role != self.Role.JOURNALIST:
            return None
        return self.articles.filter(publisher__isnull=True)

    @property
    def independent_newsletters(self):
        """Return independent journalist newsletters, otherwise None."""
        if self.role != self.Role.JOURNALIST:
            return None
        return self.newsletters.filter(publisher__isnull=True)


class Publisher(models.Model):
    """A named publisher with journalist and editor memberships.

    The name is unique and description is optional. Membership choices
    are restricted by role in forms/admin. Readers subscribe through
    User.followed_publishers rather than copied subscriber records.
    """

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(max_length=3000, blank=True)
    journalists = models.ManyToManyField(
        User,
        related_name="journalist_publishers",
        blank=True,
        limit_choices_to={"role": "journalist"},
    )
    editors = models.ManyToManyField(
        User,
        related_name="editor_publishers",
        blank=True,
        limit_choices_to={"role": "editor"},
    )

    def __str__(self):
        """Use the publisher's name in selection controls."""
        return self.name


class Article(models.Model):
    """A titled article with a journalist author and approval state.

    New articles start as drafts. publisher may be NULL for independent
    work; clean checks the author's role and publisher membership.
    Forms call model validation; API serializers perform corresponding
    checks. Deleting a publisher preserves the article and its author.
    """

    title = models.CharField(max_length=200)
    content = models.TextField(max_length=30000)
    author = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="articles"
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        permissions = [("approve_article", "Can approve article")]

    def clean(self):
        """Reject non-journalist authors and unrelated publisher
        assignments."""
        super().clean()
        if self.author_id and self.author.role != User.Role.JOURNALIST:
            raise ValidationError({"author": "Choose a journalist."})
        if (
            self.publisher_id
            and self.author_id
            and not (
                self.publisher.journalists.filter(pk=self.author_id).exists()
            )
        ):
            raise ValidationError({"publisher": "Author is not a member."})

    def __str__(self):
        """Use the title in admin lists and newsletter selections."""
        return self.title


class Newsletter(models.Model):
    """A collection with an author, description and article links.

    Journalists and editors may author newsletters. clean checks the
    role and optional publisher membership. Forms allow approved article
    selections. Display/API code also filters drafts because a linked
    article may return to draft after the newsletter has been saved.
    """

    title = models.CharField(max_length=200)
    description = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="newsletters"
    )
    publisher = models.ForeignKey(
        Publisher, on_delete=models.SET_NULL, null=True, blank=True
    )
    articles = models.ManyToManyField(Article, related_name="newsletters")

    def clean(self):
        """Disallow reader-authored newsletters and unrelated
        publishers."""
        super().clean()
        if self.author_id and self.author.role == User.Role.READER:
            raise ValidationError({"author": "Choose a journalist or editor."})
        if self.publisher_id and self.author_id:
            members = (
                self.publisher.editors
                if self.author.role == User.Role.EDITOR
                else self.publisher.journalists
            )
            if not members.filter(pk=self.author_id).exists():
                raise ValidationError({"publisher": "Author is not a member."})

    def __str__(self):
        """Use a concise newsletter label in the administration site."""
        return self.title


class ApprovalDelivery(models.Model):
    """Store one approval-delivery record and its recipient snapshot.

    A unique article relation prevents competing delivery ledgers.
    email_sent and http_sent track the steps separately; last_error
    records a pending delivery message. The service retries incomplete
    steps without repeating an already-recorded successful mail send.
    """

    article = models.OneToOneField(
        Article, on_delete=models.CASCADE, related_name="delivery"
    )
    recipients = models.JSONField(default=list)
    email_sent = models.BooleanField(default=False)
    http_sent = models.BooleanField(default=False)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ApprovalLog(models.Model):
    """Record when the internal API first logged an approved article.

    The unique article relation makes repeated HTTP POSTs idempotent.
    The receiver checks the server secret and approval state before
    creating this record. received_at is the first receipt timestamp.
    """

    article = models.OneToOneField(Article, on_delete=models.CASCADE)
    received_at = models.DateTimeField(auto_now_add=True)
