"""Browser forms with explicit field allowlists and role-scoped
choices."""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Article, Newsletter, Publisher, User


class RegistrationForm(UserCreationForm):
    """Register a reader or journalist using Django's password checks.

    The public role field has no editor option; a trusted administrator
    assigns that role. Email is normalised and checked for duplicates.
    The shared template supplies labels, help text and errors for the
    generated Django form widgets.
    """

    role = forms.ChoiceField(
        choices=[("reader", "Reader"), ("journalist", "Journalist")]
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role"]

    def clean_email(self):
        """Normalise addresses and reject case-insensitive duplicate
        accounts."""
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email.")
        return email


class ArticleForm(forms.ModelForm):
    """Edit an article's title, content and permitted publisher.

    author and approved are excluded to prevent identity/approval
    changes through submitted fields. Pass an instance with its author
    already assigned. __init__ filters publishers to that author and
    gives the content textarea 12 rows for longer drafts.

    Bind data using ModelForm arguments. For new articles,
    pass ``instance=Article(author=request.user)`` before is_valid(), so
    affiliation validation sees the server-assigned identity.
    A failed form retains field errors for the shared browser template.
    """

    class Meta:
        model = Article
        fields = ["title", "content", "publisher"]

    def __init__(self, *args, **kwargs):
        """Restrict publisher choices to the instance author's
        memberships."""
        super().__init__(*args, **kwargs)
        self.fields["publisher"].queryset = Publisher.objects.filter(
            journalists=self.instance.author_id
        )
        self.fields["content"].widget.attrs["rows"] = 12


class NewsletterForm(forms.ModelForm):
    """Edit newsletter details and select its approved articles.

    Pass an instance with its author assigned. Publisher choices depend
    on the author's journalist/editor memberships. Articles use a
    checkbox group filtered to approved records; the template wraps it
    in a labelled fieldset. The author is never a submitted field.
    """

    class Meta:
        model = Newsletter
        fields = ["title", "description", "publisher", "articles"]
        widgets = {"articles": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        """Filter affiliations using the saved or server-assigned
        author."""
        super().__init__(*args, **kwargs)
        author = self.instance.author
        membership = (
            "editors" if author.role == User.Role.EDITOR else "journalists"
        )
        self.fields["publisher"].queryset = Publisher.objects.filter(
            **{
                membership: author,
            }
        )
        self.fields["articles"].queryset = Article.objects.filter(
            approved=True
        )


class SubscriptionForm(forms.ModelForm):
    """Choose the logged-in reader's publishers and journalists.

    Both fields use labelled checkbox groups. Journalist choices exclude
    inactive accounts and non-journalists. No identity or role field is
    exposed; the view binds request.user and checks reader access before
    displaying or saving this form.
    """

    class Meta:
        model = User
        fields = ["followed_publishers", "followed_journalists"]
        labels = {
            "followed_publishers": "Publishers",
            "followed_journalists": "Journalists",
        }
        widgets = {
            "followed_publishers": forms.CheckboxSelectMultiple,
            "followed_journalists": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        """Do not offer inactive or non-journalist users as
        subscriptions."""
        super().__init__(*args, **kwargs)
        self.fields["followed_journalists"].queryset = User.objects.filter(
            role=User.Role.JOURNALIST, is_active=True
        )
