"""Editorial permissions, subscription privacy and notification retry
tests."""

from unittest.mock import Mock, patch

from django.core import mail
from django.test import LiveServerTestCase, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
import requests

from .models import ApprovalLog, Article, Newsletter, Publisher, User
from .services import approve_article


class NewsAPITests(TestCase):
    """Use real tokens and persisted role fixtures to test the public
    API."""

    def setUp(self):
        """Create one account per role and a separate journalist for
        isolation."""
        self.reader = User.objects.create_user(
            "reader", email="reader@example.test", role="reader"
        )
        self.author = User.objects.create_user(
            "author", email="author@example.test", role="journalist"
        )
        self.other = User.objects.create_user(
            "other", email="other@example.test", role="journalist"
        )
        self.editor = User.objects.create_user(
            "editor", email="editor@example.test", role="editor"
        )
        self.publisher = Publisher.objects.create(name="Bay News")
        self.publisher.journalists.add(self.author)
        self.publisher.editors.add(self.editor)
        self.article = Article.objects.create(
            title="Bay transport",
            content="Local reporting.",
            author=self.author,
            publisher=self.publisher,
        )
        self.client = APIClient()

    def authenticate(self, user):
        """Exercise actual token parsing rather than bypass
        authentication."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_role_groups_and_permissions(self):
        """Assign role groups and reserve approval permission for
        editors."""
        self.assertTrue(self.reader.groups.filter(name="reader").exists())
        self.assertTrue(self.author.has_perm("publishing.add_article"))
        self.assertFalse(self.author.has_perm("publishing.approve_article"))
        self.assertTrue(self.editor.has_perm("publishing.approve_article"))
        self.assertIsNone(self.author.publisher_subscriptions)
        self.assertIsNone(self.reader.independent_articles)

    def test_anonymous_cannot_read_api(self):
        """Require credentials even for approved API catalogue
        access."""
        self.assertEqual(self.client.get("/api/articles/").status_code, 401)

    def test_reader_cannot_read_draft(self):
        """Do not leak a draft through either list or guessed detail
        URL."""
        self.authenticate(self.reader)
        self.assertEqual(self.client.get("/api/articles/").json(), [])
        self.assertEqual(
            self.client.get(f"/api/articles/{self.article.pk}/").status_code,
            404,
        )

    def test_journalist_create_ignores_approval_and_author(self):
        """Treat author and approval state as server-controlled
        values."""
        self.authenticate(self.author)
        response = self.client.post(
            "/api/articles/",
            {
                "title": "New story",
                "content": "Reporting",
                "author": self.other.pk,
                "approved": True,
                "publisher": self.publisher.pk,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author"], self.author.pk)
        self.assertFalse(response.json()["approved"])

    def test_reader_and_editor_cannot_create_article(self):
        """Article creation is journalist-only, including for privileged
        editors."""
        for user in (self.reader, self.editor):
            self.authenticate(user)
            response = self.client.post(
                "/api/articles/",
                {
                    "title": "Denied",
                    "content": "Denied",
                },
            )
            self.assertEqual(response.status_code, 403)

    def test_foreign_publisher_rejected(self):
        """Prevent a journalist claiming affiliation with an unrelated
        publisher."""
        self.authenticate(self.other)
        response = self.client.post(
            "/api/articles/",
            {
                "title": "Wrong publisher",
                "content": "Text",
                "publisher": self.publisher.pk,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_ownership_and_editor_override(self):
        """Another journalist cannot mutate work; an editor can
        update/delete."""
        self.article.approved = True
        self.article.save()
        url = f"/api/articles/{self.article.pk}/"
        for user in (self.other, self.reader):
            self.authenticate(user)
            self.assertEqual(
                self.client.patch(url, {"title": "Stolen"}).status_code, 403
            )
            self.assertEqual(self.client.delete(url).status_code, 403)
        self.authenticate(self.editor)
        self.assertEqual(
            self.client.put(
                url,
                {
                    "title": "Edited",
                    "content": "Checked reporting",
                    "publisher": self.publisher.pk,
                },
            ).status_code,
            200,
        )
        self.article.refresh_from_db()
        self.assertFalse(self.article.approved)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_subscribed_union_and_draft_filter(self):
        """Deduplicate overlaps and exclude drafts and unsubscribed
        authors."""
        self.reader.followed_publishers.add(self.publisher)
        self.reader.followed_journalists.add(self.author)
        self.article.approved = True
        self.article.save()
        Article.objects.create(
            title="Hidden draft", content="Draft", author=self.author
        )
        Article.objects.create(
            title="Unrelated",
            content="Other",
            author=self.other,
            approved=True,
        )
        self.authenticate(self.reader)
        response = self.client.get("/api/articles/subscribed/")
        self.assertEqual(
            [row["id"] for row in response.json()], [self.article.pk]
        )

    def test_newsletter_permissions_and_drafts(self):
        """Readers cannot create and editorial collections cannot
        include drafts."""
        self.authenticate(self.reader)
        self.assertEqual(
            self.client.post(
                "/api/newsletters/",
                {
                    "title": "Reader collection",
                    "description": "Text",
                    "articles": [],
                },
                format="json",
            ).status_code,
            403,
        )
        self.authenticate(self.author)
        data = {
            "title": "Weekly",
            "description": "Local news",
            "articles": [self.article.pk],
        }
        self.assertEqual(
            self.client.post(
                "/api/newsletters/", data, format="json"
            ).status_code,
            400,
        )
        self.article.approved = True
        self.article.save()
        response = self.client.post("/api/newsletters/", data, format="json")
        self.assertEqual(response.status_code, 201)
        url = f"/api/newsletters/{response.json()['id']}/"
        self.authenticate(self.other)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.authenticate(self.editor)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Newsletter.objects.exists())

    def test_reader_cannot_approve(self):
        """Neither readers nor journalists gain publication
        authority."""
        for user in (self.reader, self.author):
            self.authenticate(user)
            response = self.client.post(
                f"/api/articles/{self.article.pk}/approve/"
            )
            self.assertEqual(response.status_code, 403)

    @override_settings(INTERNAL_APPROVAL_SECRET="test-internal-secret")
    def test_internal_receiver_authentication_and_idempotency(self):
        """Reject a missing secret, then store only one log for repeated
        POSTs."""
        url = "/api/approved/"
        data = {"article_id": self.article.pk}
        self.assertEqual(
            self.client.post(url, data, format="json").status_code, 403
        )
        self.article.approved = True
        self.article.save()
        for expected in (201, 200):
            response = self.client.post(
                url,
                data,
                format="json",
                HTTP_X_APPROVAL_SECRET="test-internal-secret",
            )
            self.assertEqual(response.status_code, expected)
        self.assertEqual(ApprovalLog.objects.count(), 1)


@override_settings(INTERNAL_APPROVAL_SECRET="test-internal-secret")
class ApprovalDeliveryTests(TestCase):
    """Verify notification intent, deduplication and retry behaviour."""

    setUp = NewsAPITests.setUp

    @patch("publishing.services.requests.post")
    def test_approval_deduplicates_and_does_not_resend(self, post):
        """A reader following both sources receives one BCC
        notification."""
        self.reader.followed_publishers.add(self.publisher)
        self.reader.followed_journalists.add(self.author)
        post.return_value = Mock()
        post.return_value.json.return_value = {"article_id": self.article.pk}
        delivery = approve_article(self.article.pk, self.editor)
        self.assertTrue(delivery.email_sent)
        self.assertTrue(delivery.http_sent)
        self.assertEqual(delivery.recipients, [self.reader.email])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, [self.reader.email])
        approve_article(self.article.pk, self.editor)
        self.assertEqual(len(mail.outbox), 1)
        post.assert_called_once()

    @patch("publishing.services.requests.post")
    def test_http_failure_retries_without_duplicate_email(self, post):
        """Keep the email completion flag when HTTP logging temporarily
        fails."""
        self.reader.followed_journalists.add(self.author)
        post.side_effect = requests.Timeout("Temporary outage")
        delivery = approve_article(self.article.pk, self.editor)
        self.assertTrue(delivery.email_sent)
        self.assertFalse(delivery.http_sent)
        self.assertTrue(delivery.last_error)
        post.side_effect = None
        post.return_value.json.return_value = {"article_id": self.article.pk}
        delivery = approve_article(self.article.pk, self.editor)
        self.assertTrue(delivery.http_sent)
        self.assertEqual(len(mail.outbox), 1)

    @patch("publishing.services.requests.post")
    @patch("publishing.services.EmailMessage.send")
    def test_email_failure_remains_retryable(self, send, post):
        """Record a failed backend delivery instead of reporting it as
        sent."""
        self.reader.followed_journalists.add(self.author)
        send.side_effect = OSError("Mail server unavailable")
        post.return_value.json.return_value = {"article_id": self.article.pk}
        delivery = approve_article(self.article.pk, self.editor)
        self.assertFalse(delivery.email_sent)
        self.assertTrue(delivery.http_sent)
        send.side_effect = None
        send.return_value = 1
        delivery = approve_article(self.article.pk, self.editor)
        self.assertTrue(delivery.email_sent)
        post.assert_called_once()

    @patch("publishing.services.requests.post")
    def test_independent_article_does_not_notify_unsubscribed_readers(
        self, post
    ):
        """A missing publisher must not match readers with no
        subscriptions."""
        self.article.publisher = None
        self.article.save()
        post.return_value.json.return_value = {"article_id": self.article.pk}
        delivery = approve_article(self.article.pk, self.editor)
        self.assertEqual(delivery.recipients, [])
        self.assertEqual(len(mail.outbox), 0)


class NewsBrowserTests(TestCase):
    """Check HTML privacy, role boundaries, form validation and
    escaping."""

    setUp = NewsAPITests.setUp

    def test_public_pages_and_private_drafts(self):
        """Render empty screens while keeping unpublished content
        private."""
        self.assertContains(self.client.get("/"), "No articles are available")
        self.assertEqual(self.client.get("/newsletters/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/articles/{self.article.pk}/").status_code, 404
        )
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
        self.assertEqual(
            self.client.get("/accounts/register/").status_code, 200
        )

    def test_public_registration_cannot_choose_editor(self):
        """Public signup must never grant a self-selected approval
        role."""
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "escalation",
                "email": "new@example.test",
                "role": "editor",
                "password1": "Strong-Test-Password-348!",
                "password2": "Strong-Test-Password-348!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="escalation").exists())

    def test_journalist_browser_create_and_edit(self):
        """A journalist creates a draft using their own publisher
        membership."""
        self.client.force_login(self.author)
        self.assertEqual(self.client.get("/articles/new/").status_code, 200)
        response = self.client.post(
            "/articles/new/",
            {
                "title": "New report",
                "content": "Checked local report",
                "publisher": self.publisher.pk,
                "approved": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(title="New report")
        self.assertEqual(article.author, self.author)
        self.assertFalse(article.approved)
        self.assertEqual(
            self.client.get(f"/articles/{article.pk}/edit/").status_code, 200
        )

    def test_reader_cannot_write_or_manage_editorial_content(self):
        """A reader session cannot mutate editorial content through
        browser routes."""
        self.client.force_login(self.reader)
        for url in (
            "/articles/new/",
            "/newsletters/new/",
            f"/articles/{self.article.pk}/edit/",
            f"/articles/{self.article.pk}/delete/",
        ):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/articles/{self.article.pk}/approve/"
            ).status_code,
            403,
        )

    def test_subscriptions_and_newsletter_forms(self):
        """Readers save only their follows; journalists can render
        newsletter forms."""
        self.client.force_login(self.reader)
        response = self.client.post(
            "/subscriptions/",
            {
                "followed_publishers": [self.publisher.pk],
                "followed_journalists": [self.author.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.reader.followed_journalists.filter(pk=self.author.pk).exists()
        )
        self.client.force_login(self.author)
        self.assertEqual(self.client.get("/subscriptions/").status_code, 403)
        self.assertEqual(self.client.get("/newsletters/new/").status_code, 200)

    def test_delete_requires_post(self):
        """Viewing a confirmation page must not destroy an article."""
        self.client.force_login(self.editor)
        url = f"/articles/{self.article.pk}/delete/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Article.objects.filter(pk=self.article.pk).exists())

    def test_csrf_and_escaped_article_html(self):
        """Reject tokenless writes and keep stored script payloads
        inert."""
        from django.test import Client

        # Enable CSRF checking explicitly; the default client skips it.
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.editor)
        self.assertEqual(
            csrf_client.post(
                f"/articles/{self.article.pk}/approve/"
            ).status_code,
            403,
        )
        # Even a published article must not execute stored HTML scripts.
        self.article.content = "<script>alert('xss')</script>"
        self.article.approved = True
        self.article.save()
        response = self.client.get(f"/articles/{self.article.pk}/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert('xss')</script>")


class PublicationHTTPTests(LiveServerTestCase):
    """Exercise the real internal HTTP receiver using a temporary local
    server."""

    setUp = NewsAPITests.setUp

    def test_approval_posts_to_own_running_api(self):
        """Commit approval before a second HTTP worker reads and logs
        it."""
        self.reader.followed_journalists.add(self.author)
        token = Token.objects.create(user=self.editor)
        with override_settings(
            INTERNAL_APPROVAL_SECRET="live-test-only-secret",
            INTERNAL_APPROVAL_URL=self.live_server_url + "/api/approved/",
        ):
            response = requests.post(
                self.live_server_url
                + f"/api/articles/{self.article.pk}/approve/",
                headers={"Authorization": f"Token {token.key}"},
                timeout=20,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["http_sent"])
        self.assertTrue(response.json()["email_sent"])
        self.assertEqual(
            ApprovalLog.objects.filter(article=self.article).count(), 1
        )
