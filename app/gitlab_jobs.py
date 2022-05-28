from django_rq import job
import gitlab
from app import models as app_models
from allauth.socialaccount import models as social_models
from app import lib as app_lib


@job
def sync_repositories_for_installation(social_account: social_models.SocialAccount):
    gitlab_instance = gitlab.Gitlab(
        oauth_token=app_lib.get_active_token(social_account).token
    )
    for project in gitlab_instance.projects.list(all=True, membership=True):
        (repo_instance, _) = app_models.Repository.objects.update_or_create(
            repo_id=project.id,
            app=social_models.SocialApp.objects.get(provider="gitlab"),
            defaults={
                "repo_name": project.name,
                "repo_full_name": project.name_with_namespace,
            },
        )
        app_models.UserRepoAccess.objects.update_or_create(
            repository=repo_instance,
            user=social_account.user,
        )
