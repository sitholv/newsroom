"""Publication workflow with persisted, independently retryable delivery
steps."""

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
import requests

from .models import ApprovalDelivery, Article, User

logger = logging.getLogger(__name__)


def approve_article(article_id, editor):
    """Approve article_id as editor and return its delivery record.

    Raise PermissionDenied for another role, or Article.DoesNotExist for
    a missing ID. Commit approval and a recipient snapshot before the
    delivery attempt so the separate HTTP receiver can read the article.
    A repeated call reuses the ledger; check its email_sent, http_sent
    and last_error fields rather than assuming every delivery succeeded.

    :param int article_id: Primary key of the article being published.
    :param editor: Authenticated user whose role must be editor.
    :type editor: publishing.models.User
    :return: Delivery ledger, including any outstanding notification errors.
    :rtype: publishing.models.ApprovalDelivery
    :raises django.core.exceptions.PermissionDenied: For a non-editor.
    :raises publishing.models.Article.DoesNotExist: For a missing article.
    """
    if editor.role != User.Role.EDITOR:
        raise PermissionDenied("Only editors may approve articles.")
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        article.approved = True
        article.save(update_fields=["approved"])
        subscriptions = Q(followed_journalists=article.author)
        # A NULL publisher must not match readers with no subscriptions.
        if article.publisher_id:
            subscriptions |= Q(followed_publishers=article.publisher_id)
        recipients = (
            User.objects.filter(
                subscriptions,
                role=User.Role.READER,
                is_active=True,
            )
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )
        delivery, _ = ApprovalDelivery.objects.get_or_create(
            article=article,
            defaults={"recipients": sorted(set(recipients))},
        )
    # Commit first so the HTTP receiver can see the approved article.
    return deliver_approval(delivery.pk)


def deliver_approval(delivery_id):
    """Retry delivery_id and return the updated delivery record.

    Lock the ledger while checking and updating each completion flag.
    Mail/HTTP failures are recorded in last_error rather than undoing
    publication; database errors are not swallowed. A successful mail
    flag is retained when only the HTTP step needs another attempt.
    This reduces retry duplicates, but SMTP is not exactly-once
    across a crash between sending and persisting the completion flag.

    :param int delivery_id: Primary key of an existing delivery ledger.
    :return: The ledger with independently persisted email/HTTP flags.
    :rtype: publishing.models.ApprovalDelivery
    :raises publishing.models.ApprovalDelivery.DoesNotExist: If missing.
    """
    with transaction.atomic():
        delivery = ApprovalDelivery.objects.select_for_update().get(
            pk=delivery_id
        )
        article = delivery.article
        errors = []
        if not delivery.email_sent:
            try:
                if delivery.recipients:
                    # BCC keeps other subscribers' addresses private.
                    count = EmailMessage(
                        subject=f"New article: {article.title}",
                        body=f"{article.title}\n\n{article.content}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        bcc=delivery.recipients,
                    ).send(fail_silently=False)
                    if count != 1:
                        raise RuntimeError(
                            "The mail backend did not accept the email."
                        )
                delivery.email_sent = True
            except Exception as error:
                logger.warning("Approval email failed: %s", error)
                errors.append("Subscriber email is awaiting delivery.")
        if not delivery.http_sent:
            try:
                if not settings.INTERNAL_APPROVAL_SECRET:
                    raise RuntimeError(
                        "Internal approval secret is not configured."
                    )
                response = requests.post(
                    settings.INTERNAL_APPROVAL_URL,
                    json={"article_id": article.pk},
                    headers={
                        "X-Approval-Secret": settings.INTERNAL_APPROVAL_SECRET
                    },
                    timeout=(3.05, 10),
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("article_id") != article.pk:
                    raise ValueError("Unexpected internal endpoint response.")
                delivery.http_sent = True
            except (
                requests.RequestException,
                ValueError,
                RuntimeError,
                AttributeError,
            ) as error:
                logger.warning("Approval HTTP logging failed: %s", error)
                errors.append(
                    "Internal HTTP publication log is awaiting delivery."
                )
        delivery.last_error = " ".join(errors)
        delivery.save(update_fields=["email_sent", "http_sent", "last_error"])
    return delivery
