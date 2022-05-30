from django.urls import path, include

from . import views
from . import github_views
from . import gitlab_views

gitlab_urlpatterns = [
    path(
        "webhook-callback/",
        gitlab_views.WebhookCallback.as_view(),
        name="gitlab_webhook_callback",
    ),
]
urlpatterns = [
    path("callback/", github_views.AuthCallback.as_view()),
    path("webhook-callback/", github_views.WebhookCallback.as_view()),
    path("oauth-callback/", github_views.OauthCallback.as_view()),
    path("marketplace-callback/", github_views.MarketplaceCallbackView.as_view()),
    path("gitlab/", include(gitlab_urlpatterns)),
]
