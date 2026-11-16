"""Token-authenticated editorial endpoints and private publication
receiver."""

from secrets import compare_digest

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import ApprovalLog, Article, Newsletter, Publisher, User
from .serializers import (
    ArticleSerializer,
    NewsletterSerializer,
    PublisherSerializer,
    UserSerializer,
)
from .services import approve_article


def visible_articles(user):
    """Readers see approved articles; journalists also see their own
    drafts."""
    queryset = Article.objects.select_related("author", "publisher")
    if user.role == User.Role.EDITOR:
        return queryset
    if user.role == User.Role.JOURNALIST:
        return queryset.filter(Q(approved=True) | Q(author=user))
    return queryset.filter(approved=True)


def require_editorial_owner(user, item):
    """Permit editor overrides, otherwise require journalist
    ownership."""
    if user.role == User.Role.EDITOR:
        return
    if user.role != User.Role.JOURNALIST or item.author_id != user.pk:
        raise PermissionDenied("You cannot change this item.")


class ArticleList(generics.ListCreateAPIView):
    """GET approved stories; POST a journalist-owned draft."""

    serializer_class = ArticleSerializer
    queryset = Article.objects.filter(approved=True).select_related(
        "author", "publisher"
    )

    def perform_create(self, serializer):
        """Never permit readers or editors to create a journalist's
        article."""
        if self.request.user.role != User.Role.JOURNALIST:
            raise PermissionDenied("Only journalists may create articles.")
        serializer.save(author=self.request.user, approved=False)


class SubscribedArticles(generics.ListAPIView):
    """GET only approved work matching a reader's current
    subscriptions."""

    serializer_class = ArticleSerializer

    def get_queryset(self):
        """Use DISTINCT because publisher and author subscriptions can
        overlap."""
        user = self.request.user
        if user.role != User.Role.READER:
            raise PermissionDenied("Subscriptions are available to readers.")
        return (
            Article.objects.filter(approved=True)
            .filter(
                Q(author__in=user.followed_journalists.all())
                | Q(publisher__in=user.followed_publishers.all())
            )
            .distinct()
        )


class ArticleDetail(generics.RetrieveUpdateDestroyAPIView):
    """Read visible content and enforce role/ownership on every
    mutation."""

    serializer_class = ArticleSerializer

    def get_queryset(self):
        """Apply draft privacy even when the caller guesses a valid
        ID."""
        return visible_articles(self.request.user)

    def perform_update(self, serializer):
        """Edited articles need editorial approval again, regardless of
        client flags."""
        require_editorial_owner(self.request.user, serializer.instance)
        serializer.save(approved=False)

    def perform_destroy(self, instance):
        """Check ownership before deleting the selected article."""
        require_editorial_owner(self.request.user, instance)
        instance.delete()


class NewsletterList(generics.ListCreateAPIView):
    """List newsletter collections; editorial accounts can create their
    own."""

    serializer_class = NewsletterSerializer
    queryset = Newsletter.objects.prefetch_related("articles").order_by(
        "-created_at"
    )

    def perform_create(self, serializer):
        """Reject reader writes and bind the author to the authenticated
        user."""
        if self.request.user.role == User.Role.READER:
            raise PermissionDenied("Readers cannot create newsletters.")
        serializer.save(author=self.request.user)


class NewsletterDetail(generics.RetrieveUpdateDestroyAPIView):
    """Read newsletters and restrict editing/deletion to editorial
    owners."""

    serializer_class = NewsletterSerializer
    queryset = Newsletter.objects.prefetch_related("articles")

    def perform_update(self, serializer):
        """Apply the same ownership policy used by HTML editorial
        screens."""
        require_editorial_owner(self.request.user, serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        """Prevent readers or another journalist deleting this
        collection."""
        require_editorial_owner(self.request.user, instance)
        instance.delete()


class PublisherList(generics.ListAPIView):
    """List publisher identities and membership IDs for authenticated
    clients."""

    serializer_class = PublisherSerializer
    queryset = Publisher.objects.order_by("name")


class JournalistList(generics.ListAPIView):
    """List public journalist identities without exposing private user
    fields."""

    serializer_class = UserSerializer
    queryset = User.objects.filter(role=User.Role.JOURNALIST).order_by(
        "username"
    )


@api_view(["POST"])
def approve(request, pk):
    """Approve an article as an editor; return accurate delivery
    state."""
    if request.user.role != User.Role.EDITOR:
        raise PermissionDenied("Only editors may approve articles.")
    article = get_object_or_404(Article, pk=pk)
    delivery = approve_article(article.pk, request.user)
    return Response(
        {
            "approved": True,
            "email_sent": delivery.email_sent,
            "http_sent": delivery.http_sent,
            "delivery_error": delivery.last_error,
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def approved_receiver(request):
    """Authenticate a server-to-server POST and idempotently log
    approval."""
    expected = settings.INTERNAL_APPROVAL_SECRET
    supplied = request.headers.get("X-Approval-Secret", "")
    # Empty configuration never grants access to an empty header.
    if not expected or not compare_digest(expected, supplied):
        raise PermissionDenied("Invalid internal approval credentials.")
    article_id = request.data.get("article_id")
    if type(article_id) is not int or article_id < 1:
        raise ValidationError(
            {"article_id": "A positive integer is required."}
        )
    article = get_object_or_404(Article, pk=article_id, approved=True)
    _, created = ApprovalLog.objects.get_or_create(article=article)
    return Response(
        {"article_id": article.pk, "logged": True},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
