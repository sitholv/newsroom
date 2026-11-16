"""News API routes, with the subscription route before integer
details."""

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import api

app_name = "api"
urlpatterns = [
    path("token/", obtain_auth_token, name="token"),
    path("articles/", api.ArticleList.as_view(), name="articles"),
    path(
        "articles/subscribed/",
        api.SubscribedArticles.as_view(),
        name="subscribed",
    ),
    path("articles/<int:pk>/", api.ArticleDetail.as_view(), name="article"),
    path("articles/<int:pk>/approve/", api.approve, name="approve"),
    path("approved/", api.approved_receiver, name="approved-receiver"),
    path("newsletters/", api.NewsletterList.as_view(), name="newsletters"),
    path(
        "newsletters/<int:pk>/",
        api.NewsletterDetail.as_view(),
        name="newsletter",
    ),
    path("publishers/", api.PublisherList.as_view(), name="publishers"),
    path("journalists/", api.JournalistList.as_view(), name="journalists"),
]
