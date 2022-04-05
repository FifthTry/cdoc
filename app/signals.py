import logging

import github
from . import lib as app_lib
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from . import models as app_models

logger = logging.getLogger(__name__)


@receiver(
    post_save,
    sender=app_models.GithubRepoMap,
    dispatch_uid="invoke_actions_on_repo_map_save",
)
def pull_request_post_save(sender, instance, **kwargs):
    # TODO: Sync all open PRs for the documentation repository and the code repository
    installation_instance = instance.integration
    github_data_manager = app_lib.GithubDataManager(
        installation_id=installation_instance.installation_id,
        user_token=installation_instance.creator.get_active_access_token(),
    )
    github_data_manager.sync_open_prs(instance.code_repo)
    github_data_manager.sync_open_prs(instance.documentation_repo)


@receiver(
    post_save,
    sender=app_models.GithubPullRequest,
    dispatch_uid="invoke_actions_on_pr_update",
)
def pull_request_post_save(sender, instance, **kwargs):
    for documentation_pr in app_models.MonitoredPullRequest.objects.filter(
        documentation_pull_request=instance
    ).iterator():
        if (
            documentation_pr.pull_request_status
            == app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
        ):
            documentation_pr.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.STALE_CODE
            )
        documentation_pr.save()
    for code_pr in app_models.MonitoredPullRequest.objects.filter(
        code_pull_request=instance
    ).iterator():
        if (
            code_pr.pull_request_status
            == app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
        ):
            code_pr.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.STALE_APPROVAL
            )
        code_pr.save()


@receiver(
    post_save,
    sender=app_models.MonitoredPullRequest,
    dispatch_uid="invoke_github_check_for_pr",
)
def update_check_run(sender, instance, **kwargs):
    (instance, is_new) = app_models.GithubCheckRun.objects.get_or_create(
        ref_pull_request=instance, run_sha=instance.code_pull_request.pr_head_commit_sha
    )
    if is_new:
        # Here, we can close the previous checks if any
        # app_models.GithubCheckRun.objects.filter(ref_pull_request=instance).exclude(
        #     run_sha=instance.code_pull_request.pr_head_commit_sha,
        # )
        pass
    else:
        instance.save()


@receiver(
    post_save, sender=app_models.GithubCheckRun, dispatch_uid="update_github_check"
)
def synchronize_github_check(sender, instance, **kwargs):
    token = (
        instance.ref_pull_request.code_pull_request.repository.owner.creator.access_token
    )
    github_app_instance = github.Github(token)
    github_repo = github_app_instance.get_repo(
        instance.ref_pull_request.code_pull_request.repository.repo_id
    )
    check_run = github_repo.get_check_run(instance.run_id)

    data = {
        "name": "continuous documentation test",
        "head_sha": instance.run_sha,
        "external_id": instance.unique_id.__str__(),
        "status": "completed",
        "conclusion": "action_required",
        "details_url": f"{settings.WEBSITE_HOST}/{github_repo.full_name}/pull/{instance.ref_pull_request.code_pull_request.pr_number}",
    }
    if (
        instance.ref_pull_request.pull_request_status
        == app_models.MonitoredPullRequest.PullRequestStatus.NOT_CONNECTED
    ):
        # Update the action with the PR connection action
        data.update(
            {
                "conclusion": "action_required",
                "output": {
                    "title": "Documentation PR is not connected",
                    "summary": "Please connect the documentation PR",
                    "text": "You can connect the documentation PR by clicking on the button below.",
                },
            }
        )
    elif (
        instance.ref_pull_request.pull_request_status
        == app_models.MonitoredPullRequest.PullRequestStatus.APPROVED
    ):
        data.update({"conclusion": "success"})
    elif instance.ref_pull_request.pull_request_status in [
        app_models.MonitoredPullRequest.PullRequestStatus.APPROVAL_PENDING,
        app_models.MonitoredPullRequest.PullRequestStatus.STALE_APPROVAL,
        app_models.MonitoredPullRequest.PullRequestStatus.STALE_CODE,
    ]:
        # Update the action with the PR approval action
        data.update(
            {
                "conclusion": "action_required",
                "output": {
                    "title": "Approve the PR on CDOC",
                    "summary": "Please approve the PR on CDOC",
                    "text": "You can connect the documentation PR by clicking on the button below.",
                },
            }
        )
    logger.info("Updating github check with data", extra={"payload": data})
    check_run_instance = check_run.edit(**data)
    logger.info("Updated the check run", extra={"response": check_run_instance})