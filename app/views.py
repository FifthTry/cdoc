import datetime
import json
import logging
import uuid
from distutils.command.clean import clean
from typing import Any, Dict
from urllib.parse import parse_qs
from django.db.models import Q
from django.urls import reverse
import django_rq
import github
import requests
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth import models as auth_models
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView
from requests.models import PreparedRequest
from analytics.decorators import log_http_event
from analytics import events as analytics_events
import lib

from . import forms as app_forms
from . import jobs as app_jobs
from . import lib as app_lib
from . import models as app_models

logger = logging.getLogger(__name__)


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
                    access_group = auth_models.Group.objects.get(name="github_user")
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
                    login(request, auth_user_instance)
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
                        # installation_instance.save()
                        installation_instance.update_token()
                        # if is_new:
                        django_rq.enqueue(
                            app_jobs.sync_repositories_for_installation,
                            installation_instance,
                        )
                        app_models.GithubAppUser.objects.update_or_create(
                            github_user=github_user,
                            installation=installation_instance,
                        )
                # logger.info([x for x in user_instance.get_installations()])
                for installation in user_instance.get_installations():
                    if installation.app_id == settings.GITHUB_CREDS["app_id"]:
                        installation_instance = (
                            app_models.GithubAppInstallation.objects.get(
                                account_id=installation.target_id,
                                installation_id=installation.id,
                            )
                        )
                        app_models.GithubAppUser.objects.update_or_create(
                            github_user=github_user,
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
                lambda data: app_models.GithubAppInstallation.objects.get(
                    installation_id=data["installation"]["id"]
                )
            )
            installation_instance = get_installation_instance(payload)
            if EVENT_TYPE == "installation":
                should_save = False
                if payload["action"] == "deleted":
                    installation_instance.state = (
                        app_models.GithubAppInstallation.InstallationState.UNINSTALLED
                    )
                    should_save = True
                elif payload["action"] == "suspend":
                    installation_instance.state = (
                        app_models.GithubAppInstallation.InstallationState.SUSPENDED
                    )
                    should_save = True
                elif payload["action"] == "unsuspend":
                    installation_instance.state = (
                        app_models.GithubAppInstallation.InstallationState.INSTALLED
                    )
                    should_save = True
                if should_save:
                    installation_instance.save()
            elif EVENT_TYPE == "pull_request":
                pull_request_data = payload["pull_request"]
                (github_repo, _) = app_models.GithubRepository.objects.update_or_create(
                    repo_id=payload["repository"]["id"],
                    owner=installation_instance,
                    defaults={
                        "repo_full_name": payload["repository"]["full_name"],
                        "repo_name": payload["repository"]["name"],
                    },
                )
                (
                    pr_instance,
                    _,
                ) = app_models.GithubPullRequest.objects.update_or_create(
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
                    (
                        github_repo,
                        _,
                    ) = app_models.GithubRepository.objects.update_or_create(
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


@method_decorator(csrf_exempt, name="dispatch")
class OauthCallback(View):
    def get(self, request):
        assert False, request


@method_decorator(login_required, name="dispatch")
class AllPRView(TemplateView):
    template_name = "all_pr_for_org.html"

    @log_http_event(
        oid=1,
        okind_ekind=(analytics_events.OKind.REPOSITORY, analytics_events.EKind.GET),
    )
    def get(self, request, *args: Any, **kwargs: Any):
        github_user = request.user.github_user

        if github_user is None:
            return Http404("User not found")
        context = self.get_context_data(**kwargs)
        get_object_or_404(
            app_models.GithubAppUser,
            github_user=github_user,
            installation=context["repo_mapping"].integration,
        )
        return self.render_to_response(context)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        matches = self.request.resolver_match.kwargs
        context["all_installations"] = app_models.GithubAppInstallation.objects.filter(
            id__in=app_models.GithubAppUser.objects.filter(
                github_user=self.request.user.github_user,
            ).values_list("installation_id", flat=True),
            state=app_models.GithubAppInstallation.InstallationState.INSTALLED,
        )
        context["repo_mapping"] = app_models.GithubRepoMap.objects.get(
            code_repo__repo_full_name__iexact="{}/{}".format(
                matches["account_name"], matches["repo_name"]
            ),
            integration__in=context["all_installations"],
        )
        current_installation = context["all_installations"].get(
            account_name=matches["account_name"]
        )

        context["current_installation"] = current_installation
        context["open_prs"] = app_models.MonitoredPullRequest.objects.filter(
            code_pull_request__repository=context["repo_mapping"].code_repo,
            code_pull_request__pr_state="open",
        )
        search_query = self.request.GET.get("q")
        if search_query:
            context["open_prs"] = context["open_prs"].filter(
                Q(code_pull_request__pr_title__icontains=search_query)
                | Q(documentation_pull_request__pr_title__icontains=search_query)
            )
            context["q"] = search_query
        #     context["all_repo_map"] = context["all_repo_map"].filter(
        #         Q(code_repo__repo_full_name__icontains=search_query)
        #         | Q(documentation_repo__repo_full_name__icontains=search_query)
        #     )
        context["all_documentation_prs"] = app_models.GithubPullRequest.objects.filter(
            repository=context["repo_mapping"].documentation_repo, pr_state="open"
        )
        return context


@method_decorator(login_required, name="dispatch")
class PRView(View):
    template_name = "index.html"
    form_class = app_forms.GithubPRApprovalForm
    success_url = "."

    def get_instance(self):
        # {'account_name': 'fifthtry', 'repo_name': 'cdoc', 'pr_number': 1}
        matches = self.request.resolver_match.kwargs
        repo = app_models.GithubRepository.objects.get(
            repo_full_name__iexact=f"{matches['account_name']}/{matches['repo_name']}",
            owner__state=app_models.GithubAppInstallation.InstallationState.INSTALLED,
        )
        pr = app_models.GithubPullRequest.objects.get(
            pr_number=matches["pr_number"], repository=repo
        )
        return app_models.MonitoredPullRequest.objects.get(code_pull_request=pr)

    def get_okind_ekind(view, request, *args, **kwargs):
        payload = json.loads(request.body)
        action = payload["action"]
        ekind = None
        if action == "connect_documentation_pr":
            ekind = analytics_events.EKind.CONNECT
        elif action == "unlink":
            ekind = analytics_events.EKind.DISCONNECT
        elif action in ["manual_pr_approval", "approve_pr"]:
            ekind = analytics_events.EKind.APPROVE
        return (analytics_events.OKind.PULL_REQUEST, ekind)

    @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def post(self, request, *args, **kwargs):
        payload = json.loads(request.body)
        instance = self.get_instance()
        old_status = instance.pull_request_status
        get_object_or_404(
            app_models.GithubAppUser,
            github_user=request.user.github_user,
            installation=instance.integration,
        )
        action = payload["action"]
        success = True
        if (
            action == "connect_documentation_pr"
            and "documentation_pull_request" in payload
        ):
            instance.documentation_pull_request_id = payload[
                "documentation_pull_request"
            ]
        elif (
            action == "approve_pr"
            and "approve_pull_request" in payload
            and payload["approve_pull_request"] == "APPROVED"
        ):
            assert (
                payload["github_username"] == request.user.github_user.account_name
            ), "User mismatch"
            instance.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
            )
        elif action == "unlink":
            instance.documentation_pull_request = None
        elif action == "manual_pr_approval":
            assert (
                payload["github_username"] == request.user.github_user.account_name
            ), "User mismatch"
            instance.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.MANUAL_APPROVAL
            )
        else:
            success = False
        with transaction.atomic():
            instance.save()
            if instance.is_approved:
                app_models.PrApproval.objects.create(
                    monitored_pull_request=instance, approver=request.user
                )
        django_rq.enqueue(app_jobs.monitored_pr_post_save, instance.id)
        instance.refresh_from_db()
        new_status = instance.pull_request_status
        if old_status != new_status:
            comment_msg = None  # Allowed: None, Body of the comment
            if (
                old_status
                == app_models.MonitoredPullRequest.PullRequestStatus.NOT_CONNECTED
                and new_status
                == app_models.MonitoredPullRequest.PullRequestStatus.APPROVAL_PENDING
            ):
                # Documentation PR is connected
                # Send a comment to the code PR that PR has been attached
                comment_msg = f"The [documentation pull request]({instance.documentation_pull_request.get_url()}) has been attached sucessfully."
            elif (
                new_status
                == app_models.MonitoredPullRequest.PullRequestStatus.MANUAL_APPROVAL
            ):
                # Send a comment to the code PR that PR has been approved
                comment_msg = (
                    "This pull request does not require any documentation changes."
                )
            elif (
                new_status == app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
            ):
                # Send a comment to the code PR that PR has been approved
                comment_msg = f"Approved! Code is up to date with the [documentation]({instance.documentation_pull_request.get_url()})"

            if comment_msg is not None:
                github_instance = github.Github(
                    request.user.github_user.get_active_access_token()
                )
                repo = github_instance.get_repo(
                    instance.code_pull_request.repository.repo_id
                )
                pr = repo.get_pull(instance.code_pull_request.pr_number)
                pr.create_issue_comment(comment_msg)
        return JsonResponse({"status": success})


class AppIndexPage(TemplateView):
    template_name = "index.html"

    def get_okind_ekind(view, request, *args, **kwargs):
        if request.method == "GET":
            if request.user.is_authenticated:
                return (analytics_events.OKind.ORGANIZATION, analytics_events.EKind.GET)
            else:
                return (analytics_events.OKind.VISIT, analytics_events.EKind.CREATE)
        else:
            return (analytics_events.OKind.REPOSITORY, analytics_events.EKind.CONNECT)

    @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def post(self, request, *args, **kwargs):
        payload = json.loads(request.body)
        payload["all_installations"] = app_models.GithubAppInstallation.objects.filter(
            id__in=app_models.GithubAppUser.objects.filter(
                github_user=self.request.user.github_user
            ).values_list("installation_id", flat=True),
            state=app_models.GithubAppInstallation.InstallationState.INSTALLED,
        )
        code_repo = app_models.GithubRepository.objects.get(id=payload["code_repo_id"])
        (instance, _) = app_models.GithubRepoMap.objects.update_or_create(
            integration=code_repo.owner,
            code_repo=code_repo,
            documentation_repo_id=payload["documentation_repo_id"],
            defaults={
                "integration_type": app_models.GithubRepoMap.IntegrationType.FULL,
            },
        )
        django_rq.enqueue(app_jobs.sync_prs_for_repository, payload["code_repo_id"])
        django_rq.enqueue(
            app_jobs.sync_prs_for_repository, payload["documentation_repo_id"]
        )
        return JsonResponse({"success": True})

    @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def get(self, request, *args, **kwargs) -> HttpResponse:
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            all_installations = app_models.GithubAppInstallation.objects.filter(
                id__in=app_models.GithubAppUser.objects.filter(
                    github_user=self.request.user.github_user
                ).values_list("installation_id", flat=True),
                state=app_models.GithubAppInstallation.InstallationState.INSTALLED,
            )
            context["all_installations"] = all_installations
            context["all_repo_map"] = app_models.GithubRepoMap.objects.filter(
                integration__in=all_installations
            )
            context[
                "available_repos_for_mapping"
            ] = app_models.GithubRepository.objects.filter(
                owner__in=all_installations,
                code_repos__isnull=True,
                documentation_repos__isnull=True,
            )
            context["unmapped_repos_display"] = context["available_repos_for_mapping"]
            search_query = self.request.GET.get("q")
            if search_query:
                context["all_repo_map"] = context["all_repo_map"].filter(
                    Q(code_repo__repo_full_name__icontains=search_query)
                    | Q(documentation_repo__repo_full_name__icontains=search_query)
                )
                context["unmapped_repos_display"] = context[
                    "unmapped_repos_display"
                ].filter(repo_full_name__icontains=search_query)
                context["q"] = search_query
            context["all_repo_map"] = context["all_repo_map"][:10]
            context["unmapped_repos_display"] = context["unmapped_repos_display"][:10]
        else:
            login_state_instance = app_models.GithubLoginState()
            if self.request.GET.get("next"):
                login_state_instance.redirect_url = self.request.GET.get("next")
            login_state_instance.save()
            url = "https://github.com/login/oauth/authorize"
            params = {
                "client_id": settings.GITHUB_CREDS["client_id"],
                "allow_signup": False,
                "state": login_state_instance.state.__str__(),
            }
            req = PreparedRequest()
            req.prepare_url(url, params)
            context["github_login_url"] = req.url

        return context


class InitializeGithubLogin(View):
    @log_http_event(
        oid=1,
        okind_ekind=(
            analytics_events.OKind.USER,
            analytics_events.EKind.GITHUB_HANDOVER,
        ),
    )
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
            url = "https://github.com/login/oauth/authorize"
            params = {
                "client_id": settings.GITHUB_CREDS["client_id"],
                "allow_signup": False,
                "state": login_state_instance.state.__str__(),
            }
            req = PreparedRequest()
            req.prepare_url(url, params)
            return HttpResponseRedirect(req.url)


class IndexView(TemplateView):
    template_name = "/"

    def get_context_data(self, *args, **kwargs):
        context = super(IndexView, self).get_context_data(*args, **kwargs)
        context["asd"] = "Message from context"
        return context


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
