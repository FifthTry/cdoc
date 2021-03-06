from django.urls import path

from . import views

urlpatterns = [
    path("callback/", views.AuthCallback.as_view()),
    path("webhook-callback/", views.WebhookCallback.as_view()),
    path("oauth-callback/", views.OauthCallback.as_view()),
    path("marketplace-callback/", views.MarketplaceCallbackView.as_view()),
]
