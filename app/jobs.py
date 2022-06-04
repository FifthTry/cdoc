import logging
import django

import django_rq
import github
from django.conf import settings
from django_rq import job

from app import models as app_models

from . import lib as app_lib

logger = logging.getLogger(__name__)


@job
def sync_repositories_for_installation(
    installation_instance: app_models.AppInstallation,
    social_account,
):
    logger.info(f"GithubAppInstallation signal received for {installation_instance}")
    creator = installation_instance.creator
    creator_social_account = creator.socialaccount_set.get(provider="github")
    github_manager = app_lib.GithubDataManager(
        installation_instance.installation_id,
        app_lib.get_active_token(creator_social_account).token,
    )
    new_repos = github_manager.sync_repositories()
    for repo in new_repos:
        # access_evaluation for github is pending
        app_models.UserRepoAccess.objects.update_or_create(
            repository=repo,
            social_account=social_account,
            access=50,
        )


@job
def sync_prs_for_repository(repository_id: int):
    logger.info(f"Sync PR job received for repository_id: {repository_id}")
    repository_instance = app_models.Repository.objects.get(
        repo_id=repository_id,
        app__provider="github",
    )
    highest_access_user = (
        repository_instance.userrepoaccess_set.all().order_by("-access").first()
    )
    if highest_access_user is None:
        return
    # installation_instance = instance.owner
    github_data_manager = app_lib.GithubDataManager(
        # Installation_id not required for syncing the PRs
        installation_id=None,
        user_token=app_lib.get_active_token(highest_access_user.social_account).token,
    )
    all_prs = github_data_manager.sync_open_prs(repository_instance)
    for pr_id in all_prs:
        django_rq.enqueue(on_pr_update, pr_id)


@job
def on_pr_update(pull_request_id: int):
    instance = app_models.PullRequest.objects.get(id=pull_request_id)
    for documentation_pr in app_models.MonitoredPullRequest.objects.filter(
        documentation_pull_request=instance
    ).iterator():
        if documentation_pr.is_approved:
            documentation_pr.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.STALE_CODE
            )
        documentation_pr.save()
    for code_pr in app_models.MonitoredPullRequest.objects.filter(
        code_pull_request=instance
    ).iterator():
        if code_pr.is_approved:
            code_pr.pull_request_status = (
                app_models.MonitoredPullRequest.PullRequestStatus.STALE_APPROVAL
            )
        code_pr.save()

    if instance.repository.code_repos.exists():
        # installation_instance = instance.repository.code_repos.last().integration
        (
            monitored_pr_instance,
            is_new,
        ) = app_models.MonitoredPullRequest.objects.get_or_create(
            code_pull_request=instance
        )
        if is_new is False:
            monitored_pr_instance.save()
        django_rq.enqueue(monitored_pr_post_save, monitored_pr_instance.id)


@job
def monitored_pr_post_save(instance_id: int):
    monitored_pr_instance = app_models.MonitoredPullRequest.objects.get(id=instance_id)
    (instance, is_new) = app_models.PullRequestCheck.objects.get_or_create(
        ref_pull_request=monitored_pr_instance,
        run_sha=monitored_pr_instance.code_pull_request.pr_head_commit_sha,
    )
    if is_new is False:
        # Here, we can close the previous checks if any
        # app_models.PullRequestCheck.objects.filter(ref_pull_request=instance).exclude(
        #     run_sha=instance.code_pull_request.pr_head_commit_sha,
        # )
        instance.save()
    #     django_rq.enqueue(update_github_check, cr_instance.id)

    # @job
    # def update_github_check(github_check_run_id: int):
    #     instance = app_models.PullRequestCheck.objects.get(id=github_check_run_id)
    highest_access_account = (
        instance.ref_pull_request.code_pull_request.repository.userrepoaccess_set.order_by(
            "-access"
        )
        .first()
        .social_account
    )
    token = app_lib.get_active_token(highest_access_account).token
    github_app_instance = github.Github(token)
    github_repo = github_app_instance.get_repo(
        instance.ref_pull_request.code_pull_request.repository.repo_id
    )
    # current_pr = github_repo.get_pull(
    #     instance.ref_pull_request.code_pull_request.pr_number
    # )

    check_run = github_repo.get_check_run(instance.run_id)

    data = {
        "name": settings.GITHUB_CREDS["app_name"],
        "head_sha": instance.run_sha,
        "external_id": instance.unique_id.__str__(),
        "status": "completed",
        "conclusion": "action_required",
        "details_url": f"{settings.WEBSITE_HOST}/{github_repo.full_name}/pulls/",
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
    elif instance.ref_pull_request.pull_request_status in [
        app_models.MonitoredPullRequest.PullRequestStatus.APPROVED,
        app_models.MonitoredPullRequest.PullRequestStatus.MANUAL_APPROVAL,
    ]:
        data.update(
            {
                "conclusion": "success",
                "output": {
                    "title": "",
                    "summary": "",
                    "text": "",
                },
            }
        )
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
                    "text": "You can approve the PR by heading to the cdoc platform and clicking on the button below.",
                },
            }
        )
    logger.info("Updating github check with data", extra={"payload": data})
    check_run_instance = check_run.edit(**data)
    logger.info("Updated the check run", extra={"response": check_run_instance})


@job
def merge_request_comment(
    monitored_pr_instance: app_models.MonitoredPullRequest,
    user_instance: app_models.UserRepoAccess,
    comment_message: str,
):
    github_instance = github.Github(
        app_lib.get_active_token(user_instance.social_account).token
    )
    repo = github_instance.get_repo(
        monitored_pr_instance.code_pull_request.repository.repo_id
    )
    pr = repo.get_pull(monitored_pr_instance.code_pull_request.pr_number)
    pr.create_issue_comment(comment_message)
    django_rq.enqueue(monitored_pr_post_save, monitored_pr_instance.id)
