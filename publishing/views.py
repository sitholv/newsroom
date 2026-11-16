"""HTML editorial screens with authentication, ownership and safe HTTP
methods."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from .forms import (
    ArticleForm,
    NewsletterForm,
    RegistrationForm,
    SubscriptionForm,
)
from .models import Article, Newsletter, User
from .services import approve_article


def check_owner(user, item):
    """Check whether user may change the article or newsletter item.

    Editors may manage any item; a journalist must be its author.
    Return None on success or raise PermissionDenied (HTTP 403).

    :param user: The authenticated caller, not a submitted author ID.
    :type user: publishing.models.User
    :param item: Persisted Article or Newsletter with an author_id.
    :return: None when the caller may edit the object.
    :raises django.core.exceptions.PermissionDenied: For an unauthorised user.
    """
    if user.role == User.Role.EDITOR:
        return
    if user.role != User.Role.JOURNALIST or item.author_id != user.pk:
        raise PermissionDenied("You cannot change this item.")


@require_safe
def home(request):
    """Show the reading/review list on GET or HEAD.

    Return publishing/home.html with articles. Visitors and readers see
    approved work only. Journalists also see their own drafts; editors
    see all drafts so they can review submissions.
    """
    articles = Article.objects.filter(approved=True)
    if request.user.is_authenticated:
        if request.user.role == User.Role.EDITOR:
            articles = Article.objects.all()
        elif request.user.role == User.Role.JOURNALIST:
            articles = Article.objects.filter(
                Q(approved=True) | Q(author=request.user)
            )
    articles = articles.select_related("author", "publisher")
    return render(request, "publishing/home.html", {"articles": articles})


@require_http_methods(["GET", "POST"])
def register(request):
    """Display signup or register a reader/journalist account.

    GET and invalid POST render publishing/form.html with form and
    title. A valid POST logs in the new user and redirects to home.
    Public signup cannot create an editor or assign staff permissions.
    """
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("home")
    return render(
        request,
        "publishing/form.html",
        {
            "form": form,
            "title": "Create account",
        },
    )


@require_safe
def article_detail(request, pk):
    """Display the article identified by pk on GET or HEAD.

    Return publishing/article.html with article and editable. A reader
    or visitor gets HTTP 404 for a draft, as does a journalist
    requesting another author's draft. Editable controls are only a UI
    hint; mutation views perform their own permission checks.
    """
    articles = Article.objects.filter(approved=True)
    if request.user.is_authenticated:
        if request.user.role == User.Role.EDITOR:
            articles = Article.objects.all()
        elif request.user.role == User.Role.JOURNALIST:
            articles = Article.objects.filter(
                Q(approved=True) | Q(author=request.user)
            )
    article = get_object_or_404(
        articles.select_related("author", "publisher"), pk=pk
    )
    editable = request.user.is_authenticated and (
        request.user.role == User.Role.EDITOR
        or (
            request.user.role == User.Role.JOURNALIST
            and article.author_id == request.user.pk
        )
    )
    return render(
        request,
        "publishing/article.html",
        {
            "article": article,
            "editable": editable,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def article_edit(request, pk=None):
    """Display or save an article as a draft.

    pk is None for creation or an existing article ID for editing.
    Only journalists create articles; editors or the owning journalist
    may edit. GET and invalid POST render form and title through
    publishing/form.html. Valid POST saves and redirects to article
    detail. Editing removes approval so changed content is reviewed.
    """
    if pk:
        article = get_object_or_404(Article, pk=pk)
        check_owner(request.user, article)
    else:
        if request.user.role != User.Role.JOURNALIST:
            raise PermissionDenied("Only journalists may create articles.")
        article = Article(author=request.user)
    form = ArticleForm(
        request.POST if request.method == "POST" else None, instance=article
    )
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.approved = False
        saved.save()
        messages.success(request, "Draft saved for editorial review.")
        return redirect("article", pk=saved.pk)
    return render(
        request,
        "publishing/form.html",
        {
            "form": form,
            "title": "Article details",
        },
    )


@login_required
@require_POST
def article_approve(request, pk):
    """Approve article pk and attempt its notifications using POST.

    Only an editor may call this view. Missing articles return HTTP 404.
    The service records approval before contacting mail and the internal
    API. Set a delivery-status message and redirect to article detail;
    failed notifications do not turn a saved approval into a new draft.
    """
    if request.user.role != User.Role.EDITOR:
        raise PermissionDenied("Only editors may approve articles.")
    article = get_object_or_404(Article, pk=pk)
    delivery = approve_article(article.pk, request.user)
    if delivery.last_error:
        messages.warning(request, "Article approved. " + delivery.last_error)
    else:
        messages.success(
            request, "Article approved; notification steps completed."
        )
    return redirect("article", pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def delete_content(request, kind, pk):
    """Confirm or delete editorial content owned by the caller.

    kind comes from the URL configuration and selects Article or
    Newsletter; pk selects the record. GET renders confirm.html with
    item. POST deletes and redirects to home or newsletters.
    A non-owner journalist or reader receives HTTP 403 before deletion.
    """
    model = Article if kind == "article" else Newsletter
    item = get_object_or_404(model, pk=pk)
    check_owner(request.user, item)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Content deleted.")
        return redirect("home" if kind == "article" else "newsletters")
    return render(request, "publishing/confirm.html", {"item": item})


@login_required
@require_http_methods(["GET", "POST"])
def subscriptions(request):
    """Display or save the logged-in reader's followed sources.

    GET and invalid POST render form and title through
    publishing/form.html. A valid POST saves the reader's selections
    and redirects to subscriptions. Other roles receive HTTP 403.
    The account is request.user, never a submitted user ID.
    """
    if request.user.role != User.Role.READER:
        raise PermissionDenied("Only readers can manage subscriptions.")
    form = SubscriptionForm(
        request.POST if request.method == "POST" else None,
        instance=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Subscriptions updated.")
        return redirect("subscriptions")
    return render(
        request,
        "publishing/form.html",
        {
            "form": form,
            "title": "Your subscriptions",
        },
    )


@require_safe
def newsletters(request):
    """List newsletter collections on GET or HEAD.

    Return publishing/newsletters.html with newsletters, newest first.
    This public list shows collection metadata, not draft article text.
    """
    return render(
        request,
        "publishing/newsletters.html",
        {
            "newsletters": Newsletter.objects.select_related(
                "author"
            ).order_by("-created_at"),
        },
    )


@require_safe
def newsletter_detail(request, pk):
    """Show newsletter pk and its currently approved contents.

    GET or HEAD renders publishing/newsletter.html with newsletter,
    articles and editable. Missing IDs return HTTP 404. Filtering at
    display time also hides a story that was approved when selected
    but has since returned to draft after an edit.
    """
    newsletter = get_object_or_404(Newsletter, pk=pk)
    editable = request.user.is_authenticated and (
        request.user.role == User.Role.EDITOR
        or (
            request.user.role == User.Role.JOURNALIST
            and newsletter.author_id == request.user.pk
        )
    )
    return render(
        request,
        "publishing/newsletter.html",
        {
            "newsletter": newsletter,
            "articles": newsletter.articles.filter(approved=True),
            "editable": editable,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def newsletter_edit(request, pk=None):
    """Display or save a journalist/editor's newsletter.

    pk is None for a new collection or selects an existing newsletter.
    Readers are denied; editing also checks ownership/editor status.
    GET and invalid POST render form and title through
    publishing/form.html. A valid POST redirects to newsletter detail.
    """
    if request.user.role == User.Role.READER:
        raise PermissionDenied("Readers cannot create newsletters.")
    newsletter = (
        get_object_or_404(Newsletter, pk=pk)
        if pk
        else Newsletter(author=request.user)
    )
    if pk:
        check_owner(request.user, newsletter)
    form = NewsletterForm(
        request.POST if request.method == "POST" else None, instance=newsletter
    )
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, "Newsletter saved.")
        return redirect("newsletter", pk=saved.pk)
    return render(
        request,
        "publishing/form.html",
        {
            "form": form,
            "title": "Newsletter details",
        },
    )
