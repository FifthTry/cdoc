import datetime
import json
import logging
import uuid
from distutils.command.clean import clean
from typing import Any, Dict
from urllib.parse import parse_qs

import django_rq
import github
import requests
from analytics import events as analytics_events
from analytics.decorators import log_http_event
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth import models as auth_models
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView
from requests.models import PreparedRequest
from allauth.socialaccount import models as allauth_social_models
import lib

from . import jobs as app_jobs
from . import models as app_models

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class MarketplaceCallbackView(View):
    def post(self, request, *args, **kwargs):
        body = request.body
        is_verified = lib.verify_signature(
            request.headers["X-Hub-Signature-256"],
            body,
            settings.GITHUB_CREDS["marketplace_signature_secret"],
        )
        if not is_verified:
            return HttpResponse("Invalid signature", status=403)
        payload = json.loads(body)
        app_models.GithubMarketplaceEvent.objects.create(payload=payload)
        return JsonResponse({"status": True})


@method_decorator(csrf_exempt, name="dispatch")
class AuthCallback(View):
    def get_okind_ekind(view, request, *args, **kwargs):
        if "installation_id" in request.GET:
            if request.GET.get("setup_action") == "update":
                return (
                    analytics_events.OKind.INSTALLATION,
                    analytics_events.EKind.UPDATE,
                )
            else:
                return (
                    analytics_events.OKind.INSTALLATION,
                    analytics_events.EKind.CREATE,
                )
        return (analytics_events.OKind.USER, analytics_events.EKind.LOGIN)

    @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def get(self, request, *args, **kwargs):
        """
        This method is invoked when the user installs the application and
        generates the auth token for the user to be used in the future.
        Expected inputs as urlparams:
            - code: str
            - installation_id: int
            - setup_action: str
        """
        code: str = request.GET["code"]

        # logger.info(request.GET)
        # github_app_auth_user = app_models.GithubAppAuth.objects.create(
        #     code=code,
        #     installation_id=installation_id,
        #     setup_action=setup_action,
        # )
        # Get the App installation account for managing the various scopes for a user
        # Example, User A can be a part of 2 installations. So, the user will see them as two different projects
        # in the UI.
        # The user's account using the `code` recieved in the step above
        # logger.info(request.get_host())
        social_app = allauth_social_models.SocialApp.objects.get(provider="github")
        payload = {
            "client_id": social_app.client_id,
            "client_secret": social_app.secret,
            "code": code,
            "redirect_uri": f"https://{request.get_host()}/app/callback/",
            "state": uuid.uuid4().__str__(),
        }
        resp = requests.post(
            "https://github.com/login/oauth/access_token", json=payload
        )
        logger.info(resp.text)
        if resp.ok:
            response = parse_qs(resp.text)
            if "error" in response:
                logger.error(response)
            else:
                now = timezone.now()
                access_token = response["access_token"][0]
                logger.info(response)
                access_token_expires_at = now + datetime.timedelta(
                    seconds=int(response["expires_in"][0])
                )
                refresh_token = response["refresh_token"][0]
                refresh_token_expires_at = now + datetime.timedelta(
                    seconds=int(response["refresh_token_expires_in"][0])
                )
                logger.info(access_token)
                github_instance = github.Github(access_token)
                user_instance = github_instance.get_user()
                with transaction.atomic():
                    # access_group = auth_models.Group.objects.get(name="github_user")
                    # TODO: Ideally a new user should be created/verified by email. Can lead to issues
                    (auth_user_instance, _) = get_user_model().objects.get_or_create(
                        username=user_instance.login,
                        defaults={
                            "is_active": True,
                            "is_staff": False,
                        },
                    )
                    (
                        social_account,
                        _,
                    ) = allauth_social_models.SocialAccount.objects.update_or_create(
                        user=auth_user_instance,
                        provider="github",
                        uid=user_instance.id,
                        extra_data={},
                    )
                    allauth_social_models.SocialToken.objects.update_or_create(
                        account=social_account,
                        app=social_app,
                        defaults={
                            "token": access_token,
                            "token_secret": refresh_token,
                            "expires_at": access_token_expires_at,
                        },
                    )
                    login(
                        request,
                        auth_user_instance,
                        backend="allauth.account.auth_backends.AuthenticationBackend",
                    )
                if "installation_id" in request.GET:
                    installation_id: int = request.GET["installation_id"]
                    setup_action: str = request.GET["setup_action"]

                    github_installation_manager = lib.GithubInstallationManager(
                        installation_id=installation_id, user_token=access_token
                    )
                    installation_details = (
                        github_installation_manager.get_installation_details()
                    )
                    account_details = installation_details["account"]
                    account_name = account_details["login"]
                    account_id = account_details["id"]
                    account_type = account_details["type"]
                    avatar_url = account_details["avatar_url"]

                    with transaction.atomic():

                        (
                            installation_instance,
                            is_new,
                        ) = app_models.AppInstallation.objects.update_or_create(
                            installation_id=installation_id,
                            account_id=account_id,
                            social_app=social_app,
                            defaults={
                                "account_name": account_name,
                                "state": app_models.AppInstallation.InstallationState.INSTALLED,
                                "account_type": account_type,
                                "avatar_url": avatar_url,
                                "creator": auth_user_instance,
                            },
                        )
                        # installation_instance.save()
                        # installation_instance.update_token()
                        # if is_new:
                        # django_rq.enqueue(
                        #     app_jobs.sync_repositories_for_installation,
                        #     installation_instance,
                        # )
                        app_models.AppUser.objects.update_or_create(
                            user=auth_user_instance,
                            installation=installation_instance,
                        )
                # logger.info([x for x in user_instance.get_installations()])
                for installation in user_instance.get_installations():
                    if installation.app_id == settings.GITHUB_CREDS["app_id"]:
                        installation_instance = app_models.AppInstallation.objects.get(
                            account_id=installation.target_id,
                            installation_id=installation.id,
                        )
                        app_models.AppUser.objects.update_or_create(
                            user=auth_user_instance,
                            installation=installation_instance,
                        )
        else:
            logger.error(f"Unable to get token from the code: {resp.text}")
            return HttpResponseRedirect(reverse("initiate_github_login"))
        redirect_url = None

        if "state" in request.GET:
            next_url = app_models.GithubLoginState.objects.get(
                state=request.GET["state"]
            ).redirect_url
            if next_url is not None and next_url != "":
                redirect_url = next_url
        return HttpResponseRedirect(redirect_url or "/")


@method_decorator(csrf_exempt, name="dispatch")
class WebhookCallback(View):
    def post(self, request, *args, **kwargs):
        headers = request.headers
        body = request.body
        is_verified = lib.verify_signature(
            headers["X-Hub-Signature-256"],
            body,
            settings.GITHUB_CREDS["app_signature_secret"],
        )
        payload = json.loads(body)
        if not is_verified:
            return HttpResponse("Invalid signature", status=403)
        logger.info(
            "Recieved Github webhook",
            extra={"data": {"headers": headers, "payload": payload}},
        )
        EVENT_TYPE = headers.get("X-Github-Event", None)
        # header is "installation_repositories" -> Updated the repositories installed for the installation
        interesting_events = [
            "pull_request",
            "installation_repositories",
            "check_suite",
            "installation",
        ]
        if EVENT_TYPE in interesting_events:
            get_installation_instance = (
                lambda data: app_models.AppInstallation.objects.get(
                    installation_id=data["installation"]["id"],
                    social_app__provider="github",
                )
            )
            installation_instance = get_installation_instance(payload)
            if EVENT_TYPE == "installation":
                should_save = False
                if payload["action"] == "deleted":
                    installation_instance.state = (
                        app_models.AppInstallation.InstallationState.UNINSTALLED
                    )
                    should_save = True
                elif payload["action"] == "suspend":
                    installation_instance.state = (
                        app_models.AppInstallation.InstallationState.SUSPENDED
                    )
                    should_save = True
                elif payload["action"] == "unsuspend":
                    installation_instance.state = (
                        app_models.AppInstallation.InstallationState.INSTALLED
                    )
                    should_save = True
                if should_save:
                    installation_instance.save()
            elif EVENT_TYPE == "pull_request":
                pull_request_data = payload["pull_request"]
                (github_repo, _) = app_models.Repository.objects.update_or_create(
                    repo_id=payload["repository"]["id"],
                    app=allauth_social_models.SocialApp.objects.get(provider="github"),
                    defaults={
                        "repo_full_name": payload["repository"]["full_name"],
                        "repo_name": payload["repository"]["name"],
                    },
                )
                (pr_instance, _,) = app_models.PullRequest.objects.update_or_create(
                    pr_id=pull_request_data["id"],
                    pr_number=pull_request_data["number"],
                    repository=github_repo,
                    defaults={
                        "pr_head_commit_sha": pull_request_data["head"]["sha"],
                        "pr_title": pull_request_data["title"],
                        "pr_body": pull_request_data["body"],
                        "pr_state": pull_request_data["state"],
                        "pr_created_at": pull_request_data["created_at"],
                        "pr_updated_at": pull_request_data["updated_at"],
                        "pr_merged_at": pull_request_data["merged_at"],
                        "pr_closed_at": pull_request_data["closed_at"],
                        "pr_merged": pull_request_data["merged"],
                        "pr_owner_username": pull_request_data["user"]["login"],
                    },
                )
                django_rq.enqueue(app_jobs.on_pr_update, pr_instance.id)
            elif EVENT_TYPE == "installation_repositories":
                # Repositories changed. Sync again.
                django_rq.enqueue(
                    app_jobs.sync_repositories_for_installation,
                    installation_instance,
                )
            elif EVENT_TYPE == "check_suite":
                if payload.get("action") == "requested":

                    repository_data = payload.get("repository", {})
                    (github_repo, _,) = app_models.Repository.objects.update_or_create(
                        repo_id=repository_data["id"],
                        owner=installation_instance,
                        defaults={
                            "repo_name": repository_data["name"],
                            "repo_full_name": repository_data["full_name"],
                        },
                    )
                    prs = payload.get("check_suite", {}).get("pull_requests", [])

                    head_commit_details = payload["check_suite"]["head_commit"]
                    head_commit_data = {
                        "pr_head_commit_sha": head_commit_details["id"],
                        # "pr_head_tree_sha": head_commit_details["tree_id"],
                        "pr_head_commit_message": head_commit_details["message"],
                        "pr_head_modified_on": datetime.datetime.strptime(
                            head_commit_details["timestamp"], "%Y-%m-%dT%H:%M:%S%z"
                        ),
                    }

                    logger.info(
                        f"Found PRs for commit ID: {head_commit_details['id']}",
                        extra={"data": {"pull_requests": prs}},
                    )
                    # is_documentation_repo =
                    if (
                        github_repo.code_repos.exists()
                        or github_repo.documentation_repos.exists()
                    ):
                        for pr in prs:
                            pr_id = pr.get("id")
                            pr_number = pr.get("number")
                            with transaction.atomic():
                                (
                                    pr_instance,
                                    is_new,
                                ) = app_models.GithubPullRequest.objects.update_or_create(
                                    pr_id=pr_id,
                                    pr_number=pr_number,
                                    repository=github_repo,
                                    defaults={**head_commit_data},
                                )
                                django_rq.enqueue(app_jobs.on_pr_update, pr_instance.id)
        return JsonResponse({"status": True})
