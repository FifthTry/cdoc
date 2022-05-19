from django.urls import path, include

from . import views
from . import gitlab_views

gitlab_urlpatterns = [
    path(
        "auth-callback/",
        gitlab_views.AuthCallback.as_view(),
        name="gitlab_auth_callback",
    ),
    path("initiate-login/", gitlab_views.InitiateLoginView.as_view()),
]
urlpatterns = [
    path("callback/", views.AuthCallback.as_view()),
    path("webhook-callback/", views.WebhookCallback.as_view()),
    path("oauth-callback/", views.OauthCallback.as_view()),
    path("marketplace-callback/", views.MarketplaceCallbackView.as_view()),
    path("gitlab/", include(gitlab_urlpatterns)),
]
