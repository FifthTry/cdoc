from django_rq import job
import gitlab
from app import models as app_models
from allauth.socialaccount import models as social_models
from app import lib as app_lib
from django.conf import settings


@job
def sync_repositories_for_installation(social_account: social_models.SocialAccount):
    gitlab_instance = gitlab.Gitlab(
        oauth_token=app_lib.get_active_token(social_account).token
    )
    existing_mapping = list(
        app_models.UserRepoAccess.objects.filter(
            social_account=social_account
        ).values_list("id", flat=True)
    )
    for project in gitlab_instance.projects.list(all=True, membership=True):
        (repo_instance, _) = app_models.Repository.objects.update_or_create(
            repo_id=project.id,
            app=social_models.SocialApp.objects.get(provider="gitlab"),
            defaults={
                "repo_name": project.name.replace(" ", ""),
                "repo_full_name": project.name_with_namespace.replace(" ", ""),
            },
        )
        project_perms = project._attrs["permissions"]
        user_access_level = max(
            (project_perms.get("project_access") or {}).get("access_level", 0),
            (project_perms.get("group_access") or {}).get("access_level", 0),
        )

        (instance, is_new) = app_models.UserRepoAccess.objects.update_or_create(
            repository=repo_instance,
            social_account=social_account,
            defaults={"access": user_access_level},
        )
        if is_new is False:
            existing_mapping.pop(existing_mapping.index(instance.id))
    app_models.UserRepoAccess.objects.filter(id__in=existing_mapping).update(
        access=app_models.UserRepoAccess.AccessLevel.NO_ACCESS
    )


@job
def sync_prs_for_repository(
    project_id: int,
):
    repository_instance = app_models.Repository.objects.get(
        repo_id=project_id,
        app__provider="gitlab",
    )
    highest_access_user = (
        repository_instance.userrepoaccess_set.all().order_by("-access").first()
    )
    if highest_access_user is None:
        return
    gitlab_instance = gitlab.Gitlab(
        oauth_token=app_lib.get_active_token(highest_access_user.social_account).token
    )
    project_instance = gitlab_instance.projects.get(repository_instance.repo_id)
    for merge_request in project_instance.mergerequests.list():
        try:
            head_commit = merge_request.commits().next()
        except StopIteration:
            head_commit = object()
        (pr_instance, _) = app_models.PullRequest.objects.update_or_create(
            pr_id=merge_request.id,
            pr_number=merge_request.iid,
            repository=repository_instance,
            defaults={
                "pr_title": merge_request.title,
                "pr_owner_username": merge_request.author["username"],
                "pr_head_commit_sha": getattr(head_commit, "id", None) or "",
                "pr_head_modified_on": getattr(
                    head_commit, "authored_date", merge_request.created_at
                ),
                "pr_head_commit_message": getattr(
                    head_commit, "title", merge_request.title
                )
                or "",
                "pr_body": merge_request.description,
                "pr_state": merge_request.state,
                "pr_created_at": merge_request.created_at,
                "pr_updated_at": merge_request.updated_at,
                "pr_merged_at": merge_request.merged_at,
                "pr_closed_at": merge_request.closed_at,
                "pr_merged": merge_request.state == "opened",
            },
        )
        if repository_instance.code_repos.exists():
            app_models.MonitoredPullRequest.objects.update_or_create(
                code_pull_request=pr_instance,
            )
    # Setup a webhook for this project\
    webhook_url = f"https://{settings.DEPLOYMENT_HOST_NAME}/app/gitlab/webhook-callback/"
    existing_hooks = project_instance.hooks.list()
    for hook in existing_hooks:
        if hook.url == webhook_url:
            hook.merge_requests_events = True
            hook.save()
    if len(existing_hooks) == 0:
        project_instance.hooks.create(
            {
                "url": webhook_url,
                "merge_requests_events": True,
                "push_events": False,
            }
        )
