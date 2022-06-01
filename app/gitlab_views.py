import datetime
import gitlab
from django.utils import timezone
from app import lib as app_lib
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.urls import reverse
from django.views import View
from app import models as app_models
from django.conf import settings
from requests.models import PreparedRequest
import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import time
from allauth.socialaccount import models as social_models
from app import gitlab_jobs
import django_rq
from app import jobs as app_jobs


@method_decorator(csrf_exempt, name="dispatch")
class WebhookCallback(View):
    def post(self, request, *args, **kwargs):
        headers = request.headers
        event_header = headers["X-Gitlab-Event"]
        request_body = json.loads(request.body.decode("utf-8"))
        # gitlab_instance = gitlab.Gitlab(oauth_token=app_lib.get_active_token())
        print(json.dumps(request_body))
        if (
            event_header == "Merge Request Hook"
            and request_body["object_kind"] == "merge_request"
        ):
            object_attrs = request_body["object_attributes"]
            project_name = object_attrs["target"]["path_with_namespace"]
            repo = app_models.Repository.objects.get(
                repo_full_name=project_name, app__provider="gitlab"
            )
            merge_request_id = request_body["object_attributes"]["iid"]
            old_instance = app_models.PullRequest.objects.filter(
                pr_number=merge_request_id,
                pr_id=request_body["object_attributes"]["id"],
                repository=repo,
            ).first()

            (pr_instance, _) = app_models.PullRequest.objects.update_or_create(
                pr_number=merge_request_id,
                pr_id=request_body["object_attributes"]["id"],
                repository=repo,
                defaults={
                    "pr_head_commit_sha": object_attrs["last_commit"]["id"],
                    "pr_head_modified_on": object_attrs["last_commit"]["timestamp"],
                    "pr_head_commit_message": object_attrs["last_commit"]["title"],
                    "pr_title": object_attrs["title"],
                    "pr_body": object_attrs["description"],
                    "pr_state": object_attrs["state"],
                    "pr_created_at": timezone.datetime.strptime(
                        object_attrs["created_at"], "%Y-%m-%d %H:%M:%S %Z"
                    ),
                    "pr_updated_at": timezone.datetime.strptime(
                        object_attrs["updated_at"], "%Y-%m-%d %H:%M:%S %Z"
                    ),
                },
            )
            monitored_prs = []
            try:
                monitored_pr_instance = pr_instance.monitored_code
                if old_instance.pr_head_commit_sha != pr_instance.pr_head_commit_sha:
                    monitored_pr_instance.pull_request_status = (
                        app_models.MonitoredPullRequest.PullRequestStatus.STALE_APPROVAL
                    )
                monitored_pr_instance.save()
                monitored_prs.append(monitored_pr_instance)
            except:
                pass
            for doc_pr_instance in pr_instance.monitored_documentation.all():
                # doc_pr_instance = pr_instance.monitored_code
                if old_instance.pr_head_commit_sha != pr_instance.pr_head_commit_sha:
                    doc_pr_instance.pull_request_status = (
                        app_models.MonitoredPullRequest.PullRequestStatus.STALE_CODE
                    )
                doc_pr_instance.save()
                monitored_prs.append(doc_pr_instance)
            for pr in monitored_prs:
                repo_users = (
                    pr.code_pull_request.repository.userrepoaccess_set.order_by(
                        "-access"
                    )
                )
                if repo_users.exists():
                    highest_access = repo_users.first()
                    provider_comment_action_map = {
                        "gitlab": gitlab_jobs.merge_request_comment,
                        "github": app_jobs.merge_request_comment,
                    }
                    django_rq.enqueue(
                        provider_comment_action_map[pr.repository.app.provider],
                        args=(pr, highest_access, None),
                    )
        return JsonResponse({})


@method_decorator(csrf_exempt, name="dispatch")
class GitlabPipelineRequest(View):
    def post(self, request, *args, **kwargs):
        body = json.loads(request.body.decode("utf-8"))
        gitlab_instance = gitlab.Gitlab(job_token=body["job_token"])
        # Get the job data to ensure no dirty access
        job_data = gitlab_instance.http_get("/job/")
        if job_data["pipeline"]["source"] == "merge_request_event":
            repo_instance = app_models.Repository.objects.get(
                repo_id=body["project_id"]
            )
            # This assumes the webhook has been updated prior to the pipline being invoked.
            # Potential race condition
            pr_instance = app_models.PullRequest.objects.get(
                pr_id=body["merge_request_id"],
                pr_number=body["merge_request_iid"],
                repository=repo_instance,
                pr_head_commit_sha=body["source_sha"],
            )
            return HttpResponse(0 if pr_instance.monitored_code.is_approved else 1)
        return HttpResponse(0)
