import logging
import django_rq

import github

from app import gitlab_jobs

# from app import github_jobs
from . import lib as app_lib
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from . import models as app_models
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from allauth.socialaccount import models as social_models

logger = logging.getLogger(__name__)


def new_installation(social_account):
    extra_data = social_account.extra_data
    if social_account.provider == "gitlab":
        (app_installation, _) = app_models.AppInstallation.objects.update_or_create(
            social_app=social_models.SocialApp.objects.get(
                provider=social_account.provider
            ),
            installation_id=extra_data["id"],
            creator=social_account.user,
            state=app_models.AppInstallation.InstallationState.INSTALLED,
            account_name=extra_data["username"],
            account_id=extra_data["id"],
            account_type="User",
            avatar_url=social_account.get_avatar_url(),
        )
        app_models.AppUser.objects.update_or_create(
            installation=app_installation, user=social_account.user
        )
        django_rq.enqueue(
            gitlab_jobs.sync_repositories_for_installation, social_account
        )
    elif social_account.provider == "github":
        github_instance = github.Github(app_lib.get_active_token(social_account).token)
        for installation in github_instance.get_user().get_installations():
            if installation.app_id == settings.GITHUB_CREDS["app_id"]:
                raw_data = installation.raw_data
                try:
                    app_installation = app_models.AppInstallation.objects.get(
                        social_app=social_models.SocialApp.objects.get(
                            provider=social_account.provider
                        ),
                        installation_id=installation.id,
                    )
                    app_models.AppUser.objects.update_or_create(
                        installation=app_installation, user=social_account.user
                    )
                except app_models.AppInstallation.DoesNotExist:
                    # App installation not done. Skip mapping
                    # Error: The App installation not found. Configuration error
                    pass
                # TODO: Schedule github repo sync
                # django_rq.enqueue(github_jobs., app_installation)


# def sync_repos(social_account):
#     # assert False, social_account
#     if social_account.provider == "gitlab":
#         django_rq.enqueue(gitlab_jobs.sync_repositories_for_installation)


@receiver(user_signed_up)
def _user_signed_up(request, user, *args, **kwargs):
    # User signed up. Create
    social_accounts = user.socialaccount_set.all()
    for social_account in social_accounts:
        new_installation(social_account)
        # sync_repos(social_account)


@receiver(social_account_added)
def _social_account_added(request, sociallogin, *args, **kwargs):
    new_installation(sociallogin.account)
