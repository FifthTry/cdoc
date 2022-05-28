from django.urls import path, include

from . import views
from . import github_views
from . import gitlab_views

gitlab_urlpatterns = [
    # path(
    #     "auth-callback/",
    #     gitlab_views.AuthCallback.as_view(),
    #     name="gitlab_auth_callback",
    # ),
]
urlpatterns = [
    path("callback/", github_views.AuthCallback.as_view()),
    path("webhook-callback/", github_views.WebhookCallback.as_view()),
    path("oauth-callback/", github_views.OauthCallback.as_view()),
    path("marketplace-callback/", github_views.MarketplaceCallbackView.as_view()),
    path("gitlab/", include(gitlab_urlpatterns)),
]
