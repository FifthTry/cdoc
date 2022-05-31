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
from app import gitlab_jobs
import lib

from . import forms as app_forms
from . import jobs as app_jobs
from . import lib as app_lib
from . import models as app_models

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class AllPRView(TemplateView):
    template_name = "all_pr_for_org.html"

    @log_http_event(
        oid=1,
        okind_ekind=(analytics_events.OKind.REPOSITORY, analytics_events.EKind.GET),
    )
    def get(self, request, *args: Any, **kwargs: Any):
        # github_user = request.user.github_user

        # if github_user is None:
        #     return Http404("User not found")
        context = self.get_context_data(**kwargs)
        # get_object_or_404(
        #     app_models.GithubAppUser,
        #     github_user=github_user,
        #     installation=context["repo_mapping"].integration,
        # )
        return self.render_to_response(context)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        matches = self.request.resolver_match.kwargs
        context["repo_mapping"] = app_models.MonitoredRepositoryMap.objects.get(
            code_repo__repo_full_name__iexact=matches["repo_full_name"],
        )
        context["open_prs"] = app_models.MonitoredPullRequest.objects.filter(
            code_pull_request__repository=context["repo_mapping"].code_repo,
            code_pull_request__pr_state__in=["open", "opened"],
            # open for Github, Opened for gitlab
        )
        search_query = self.request.GET.get("q")
        if search_query:
            context["open_prs"] = context["open_prs"].filter(
                Q(code_pull_request__pr_title__icontains=search_query)
                | Q(documentation_pull_request__pr_title__icontains=search_query)
            )
            context["q"] = search_query
        context["all_documentation_prs"] = app_models.PullRequest.objects.filter(
            repository=context["repo_mapping"].documentation_repo,
            pr_state__in=["open", "opened"],
        )
        social_account = (
            context["repo_mapping"]
            .code_repo.userrepoaccess_set.filter(social_account__user=self.request.user)
            .order_by("-access")
            .first()
            .social_account
        )
        user_name = None
        if social_account.provider == "github":
            user_name = social_account.extra_data["login"]
        elif social_account.provider == "gitlab":
            user_name = social_account.extra_data["username"]
        context["repo_user_name"] = user_name
        return context


@method_decorator(login_required, name="dispatch")
class PRView(View):
    template_name = "index.html"
    form_class = app_forms.GithubPRApprovalForm
    success_url = "."

    def get_instance(self):
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
        matches = self.request.resolver_match.kwargs
        # print(payload)
        # print(matches)
        repo = app_models.Repository.objects.get(
            repo_full_name=matches["repo_full_name"], app__provider=matches["provider"]
        )
        highest_access_for_user = (
            app_models.UserRepoAccess.objects.filter(
                repository=repo, social_account__user=request.user
            )
            .order_by("-access")
            .first()
        )
        pr = app_models.PullRequest.objects.get(
            repository=repo, pr_number=matches["pr_number"]
        )
        instance = pr.monitored_code
        old_status = instance.pull_request_status
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
            # assert (
            #     payload["github_username"] == request.user.github_user.account_name
            # ), "User mismatch"
            instance.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
            )
        elif action == "unlink":
            instance.documentation_pull_request = None
        elif action == "manual_pr_approval":
            # assert (
            #     payload["github_username"] == request.user.github_user.account_name
            # ), "User mismatch"
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
        post_save_provider_action_map = {
            "gitlab": gitlab_jobs.monitored_pr_post_save,
            # "github": app_jobs.monitored_pr_post_save,
        }
        # instance.refresh_from_db()
        # django_rq.enqueue(
        #     post_save_provider_action_map[matches["provider"]],
        #     args=(instance, highest_access_for_user, old_status),
        # )
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
                comment_msg = "Approved! This pull request does not require any documentation changes."
            elif (
                new_status == app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
            ):
                # Send a comment to the code PR that PR has been approved
                comment_msg = f"Approved! Code is up to date with the [documentation]({instance.documentation_pull_request.get_url()})"

            if comment_msg is not None:
                provider_comment_action_map = {
                    "gitlab": gitlab_jobs.merge_request_comment,
                    # "github": app_jobs.merge_request_comment,
                }
                django_rq.enqueue(
                    provider_comment_action_map[matches["provider"]],
                    args=(instance, highest_access_for_user, comment_msg),
                )
        #         github_instance = github.Github(
        #             request.user.github_user.get_active_access_token()
        #         )
        #         repo = github_instance.get_repo(
        #             instance.code_pull_request.repository.repo_id
        #         )
        #         pr = repo.get_pull(instance.code_pull_request.pr_number)
        #         pr.create_issue_comment(comment_msg)
        return JsonResponse({"status": success})


class AppIndexPage(TemplateView):
    template_name = "index.html"

    # def get_okind_ekind(view, request, *args, **kwargs):
    #     if request.method == "GET":
    #         if request.user.is_authenticated:
    #             return (analytics_events.OKind.ORGANIZATION, analytics_events.EKind.GET)
    #         else:
    #             return (analytics_events.OKind.VISIT, analytics_events.EKind.CREATE)
    #     else:
    #         return (analytics_events.OKind.REPOSITORY, analytics_events.EKind.CONNECT)

    # @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def post(self, request, *args, **kwargs):
        payload = json.loads(request.body)
        (instance, _) = app_models.MonitoredRepositoryMap.objects.update_or_create(
            code_repo_id=payload["code_repo_id"],
            documentation_repo_id=payload["documentation_repo_id"],
            defaults={
                "integration_type": app_models.MonitoredRepositoryMap.IntegrationType.FULL,
            },
        )
        sync_job = {
            "gitlab": gitlab_jobs.sync_prs_for_repository,
            "github": app_jobs.sync_prs_for_repository,
        }
        django_rq.enqueue(
            sync_job[instance.code_repo.app.provider], instance.code_repo.repo_id
        )
        django_rq.enqueue(
            sync_job[instance.documentation_repo.app.provider],
            instance.documentation_repo.repo_id,
        )

        # TODO: Sync Open PRs for the repositories
        # TODO: Setup the webhook for the mapped repositories
        # django_rq.enqueue(app_jobs.sync_prs_for_repository, payload["code_repo_id"])
        # django_rq.enqueue(
        #     app_jobs.sync_prs_for_repository, payload["documentation_repo_id"]
        # )
        return JsonResponse({"success": True})

    # @log_http_event(oid=1, okind_ekind=get_okind_ekind)
    def get(self, request, *args, **kwargs) -> HttpResponse:
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["all_repo_map"] = app_models.MonitoredRepositoryMap.objects.filter(
                code_repo__userrepoaccess__social_account__user=self.request.user,
                code_repo__userrepoaccess__access__gte=app_models.UserRepoAccess.AccessLevel.MINIMAL,
                documentation_repo__userrepoaccess__social_account__user=self.request.user,
                documentation_repo__userrepoaccess__access__gte=app_models.UserRepoAccess.AccessLevel.MINIMAL,
            )
            context[
                "available_repos_for_mapping"
            ] = app_models.Repository.objects.filter(
                userrepoaccess__social_account__user=self.request.user,
                userrepoaccess__access__gte=app_models.UserRepoAccess.AccessLevel.MINIMAL,
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
        return context


class IndexView(TemplateView):
    template_name = "/"

    def get_context_data(self, *args, **kwargs):
        context = super(IndexView, self).get_context_data(*args, **kwargs)
        context["asd"] = "Message from context"
        return context
