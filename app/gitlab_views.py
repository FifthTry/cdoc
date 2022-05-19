from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View
from app import models as app_models
from django.conf import settings
from requests.models import PreparedRequest
import base64
import hashlib
import requests


class InitiateLoginView(View):
    def get(self, request, *args, **kwargs):
        if self.request.user.is_authenticated:
            if request.GET.get("next"):
                return HttpResponseRedirect(request.GET.get("next"))
            return HttpResponseRedirect("/")
        else:
            login_state_instance = app_models.GithubLoginState()
            if self.request.GET.get("next"):
                login_state_instance.redirect_url = self.request.GET.get("next")
            login_state_instance.save()
            url = "https://gitlab.com/oauth/authorize"
            # https://gitlab.example.com/oauth/authorize?redirect_uri=REDIRECT_URI&scope=REQUESTED_SCOPES&code_challenge=CODE_CHALLENGE&code_challenge_method=S256
            params = {
                "client_id": settings.GITLAB_CREDS["application_id"],
                "response_type": "code",
                "allow_signup": False,
                "state": login_state_instance.state.__str__(),
                "code_challenge": (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(
                            (login_state_instance.state.__str__() * 2).encode("ascii")
                        ).digest()
                    )
                    .decode("ascii")
                    .rstrip("=")
                ),
                "code_challenge_method": "S256",
                "scope": settings.GITLAB_CREDS["scope"],
                "redirect_uri": request.build_absolute_uri(
                    reverse("gitlab_auth_callback")
                ),
            }
            req = PreparedRequest()
            req.prepare_url(url, params)
            return HttpResponseRedirect(req.url)


class AuthCallback(View):
    def get(self, request, *args, **kwargs):
        code = request.GET["code"]
        state = request.GET["state"]
        # assert False, (code, state)
        # parameters = 'client_id=APP_ID&code=RETURNED_CODE&grant_type=authorization_code&redirect_uri=REDIRECT_URI&code_verifier=CODE_VERIFIER'
        payload = {
            "client_id": settings.GITLAB_CREDS["application_id"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": request.build_absolute_uri(reverse("gitlab_auth_callback")),
            "code_verifier": state * 2,
        }
        response = requests.post("https://gitlab.com/oauth/token", json=payload)
        assert False, response.text

        pass
