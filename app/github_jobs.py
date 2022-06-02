import logging
import django

import django_rq
import github
from django.conf import settings
from django_rq import job

from app import models as app_models
from allauth.socialaccount import models as social_models

from app import lib as app_lib

logger = logging.getLogger(__name__)


@job
def sync_repositories_for_installation(social_account: social_models.SocialAccount):
    github_instance = github.Github(social_account.socialtoken_set.last())
    existing_mapping = list(
        app_models.UserRepoAccess.objects.filter(
            social_account=social_account
        ).values_list("id", flat=True)
    )
    # for project in gitlab_instance.projects.list(all=True, membership=True):
    #     (repo_instance, _) = app_models.Repository.objects.update_or_create(
    #         repo_id=project.id,
    #         app=social_models.SocialApp.objects.get(provider="gitlab"),
    #         defaults={
    #             "repo_name": project.name.replace(" ", ""),
    #             "repo_full_name": project.path_with_namespace,
    #         },
    #     )
    #     project_perms = project._attrs["permissions"]
    #     user_access_level = max(
    #         (project_perms.get("project_access") or {}).get("access_level", 0),
    #         (project_perms.get("group_access") or {}).get("access_level", 0),
    #     )

    #     (instance, is_new) = app_models.UserRepoAccess.objects.update_or_create(
    #         repository=repo_instance,
    #         social_account=social_account,
    #         defaults={"access": user_access_level},
    #     )
    if True:
        if is_new is False:
            existing_mapping.pop(existing_mapping.index(instance.id))
    app_models.UserRepoAccess.objects.filter(id__in=existing_mapping).update(
        access=app_models.UserRepoAccess.AccessLevel.NO_ACCESS
    )
