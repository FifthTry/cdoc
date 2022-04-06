import datetime
from distutils.command.clean import clean
import json
import logging
import uuid
from urllib.parse import parse_qs

import github
import lib
from . import lib as app_lib
import requests
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import models as auth_models
from django.views.generic import FormView
from . import models as app_models
from . import forms as app_forms

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class AuthCallback(View):
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
        installation_id: int = request.GET["installation_id"]
        setup_action: str = request.GET["setup_action"]
        logger.info(request.GET)
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
        payload = {
            "client_id": settings.GITHUB_CREDS["client_id"],
            "client_secret": settings.GITHUB_CREDS["client_secret"],
            "code": code,
            "redirect_uri": f"https://{request.get_host()}/app/callback/",
            "state": uuid.uuid4().__str__(),
        }
        resp = requests.post(
            "https://github.com/login/oauth/access_token", json=payload
        )
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
                github_instance = github.Github(access_token)
                user_instance = github_instance.get_user()
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

                access_group = auth_models.Group.objects.get(name="github_user")
                with transaction.atomic():
                    (auth_user_instance, _) = get_user_model().objects.get_or_create(
                        username=user_instance.login,
                        defaults={
                            "is_active": True,
                            "is_staff": True,
                        },
                    )
                    auth_user_instance.groups.add(access_group)
                    (github_user, _) = app_models.GithubUser.objects.update_or_create(
                        account_id=user_instance.id,
                        user=auth_user_instance,
                        defaults={
                            "account_type": user_instance.type,
                            "account_name": user_instance.login,
                            "avatar_url": user_instance.avatar_url,
                        },
                    )
                    app_models.GithubUserAccessToken.objects.create(
                        token=access_token,
                        expires_at=access_token_expires_at,
                        github_user=github_user,
                    )
                    app_models.GithubUserRefreshToken.objects.create(
                        token=refresh_token,
                        expires_at=refresh_token_expires_at,
                        github_user=github_user,
                    )
                    (
                        installation_instance,
                        _,
                    ) = app_models.GithubAppInstallation.objects.update_or_create(
                        installation_id=installation_id,
                        account_id=account_id,
                        defaults={
                            "account_name": account_name,
                            "state": app_models.GithubAppInstallation.InstallationState.INSTALLED,
                            "account_type": account_type,
                            "avatar_url": avatar_url,
                            "creator": github_user,
                        },
                    )
                    login(request, auth_user_instance)
                    # installation_instance.save()
                    installation_instance.update_token()
        else:
            logger.error(resp.text)
        return HttpResponseRedirect("/admin/")


@method_decorator(csrf_exempt, name="dispatch")
class WebhookCallback(View):
    def post(self, request, *args, **kwargs):
        headers = request.headers
        payload = json.loads(request.body)
        logger.info(
            "Recieved Github webhook",
            extra={"data": {"headers": headers, "payload": payload}},
        )
        EVENT_TYPE = headers.get("X-Github-Event", None)
        # header is "installation_repositories" -> Updated the repositories installed for the installation
        get_installation_instance = (
            lambda data: app_models.GithubAppInstallation.objects.get(
                installation_id=data["installation"]["id"]
            )
        )
        installation_instance = get_installation_instance(payload)
        github_data_manager_instance = app_lib.GithubDataManager(
            installation_id=installation_instance.installation_id,
            user_token=installation_instance.creator.get_active_access_token(),
        )
        if EVENT_TYPE == "pull_request":
            pull_request_data = payload["pull_request"]
            (github_repo, _) = app_models.GithubRepository.objects.update_or_create(
                repo_id=payload["repository"]["id"],
                defaults={
                    "repo_full_name": payload["repository"]["full_name"],
                    "repo_name": payload["repository"]["name"],
                    "owner": installation_instance,
                },
            )
            (pr_instance, _) = app_models.GithubPullRequest.objects.update_or_create(
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
            if payload["action"] == "opened" and github_repo.code_repos.exists():
                (
                    monitored_pr_instance,
                    is_new,
                ) = app_models.MonitoredPullRequest.objects.get_or_create(
                    code_pull_request=pr_instance,
                )
                if is_new is False:
                    monitored_pr_instance.save()
        elif EVENT_TYPE == "installation_repositories":
            # Repositories changed. Sync again.
            github_data_manager_instance.sync_repositories()
        elif EVENT_TYPE == "check_suite":
            if payload.get("action") == "requested":

                repository_data = payload.get("repository", {})
                (github_repo, _) = app_models.GithubRepository.objects.get_or_create(
                    repo_id=repository_data["id"],
                    repo_name=repository_data["name"],
                    repo_full_name=repository_data["full_name"],
                    owner=installation_instance,
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
                            if github_repo.code_repos.exists():
                                (
                                    monitored_pr_instance,
                                    is_new,
                                ) = app_models.MonitoredPullRequest.objects.get_or_create(
                                    code_pull_request=pr_instance,
                                )
                                if is_new is False:
                                    monitored_pr_instance.save()

        return JsonResponse({"status": True})


@method_decorator(csrf_exempt, name="dispatch")
class OauthCallback(View):
    def get(self, request):
        assert False, request


class PRView(FormView):
    template_name = "app/pr_approval.html"
    form_class = app_forms.GithubPRApprovalForm
    success_url = "."

    def get_instance(self):
        # {'account_name': 'fifthtry', 'repo_name': 'cdoc', 'pr_number': 1}
        matches = self.request.resolver_match.kwargs
        repo = app_models.GithubRepository.objects.get(
            repo_full_name__iexact=f"{matches['account_name']}/{matches['repo_name']}"
        )
        pr = app_models.GithubPullRequest.objects.get(
            pr_number=matches["pr_number"], repository=repo
        )
        return app_models.MonitoredPullRequest.objects.get(code_pull_request=pr)

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()
        return form_class(instance=self.get_instance(), **self.get_form_kwargs())

    def form_valid(self, form):
        # form.instance = self.get_instance()
        # form.save()
        clean_data = form.cleaned_data
        instance = self.get_instance()
        if "documentation_pull_request" in clean_data:
            instance.documentation_pull_request = clean_data[
                "documentation_pull_request"
            ]
        else:
            instance.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
            )
        instance.save()
        return super().form_valid(form)
