"""Named browser routes for authentication and editorial workflows."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/register/", views.register, name="register"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="publishing/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("articles/new/", views.article_edit, name="article-create"),
    path("articles/<int:pk>/", views.article_detail, name="article"),
    path("articles/<int:pk>/edit/", views.article_edit, name="article-edit"),
    path(
        "articles/<int:pk>/approve/",
        views.article_approve,
        name="article-approve",
    ),
    path(
        "articles/<int:pk>/delete/",
        views.delete_content,
        {"kind": "article"},
        name="article-delete",
    ),
    path("newsletters/", views.newsletters, name="newsletters"),
    path("newsletters/new/", views.newsletter_edit, name="newsletter-create"),
    path("newsletters/<int:pk>/", views.newsletter_detail, name="newsletter"),
    path(
        "newsletters/<int:pk>/edit/",
        views.newsletter_edit,
        name="newsletter-edit",
    ),
    path(
        "newsletters/<int:pk>/delete/",
        views.delete_content,
        {"kind": "newsletter"},
        name="newsletter-delete",
    ),
]
