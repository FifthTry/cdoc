from . import models as app_models
import lib
import github
from django.utils import timezone
from requests_oauthlib import OAuth2Session
from allauth.socialaccount import models as social_models
import datetime


class GithubDataManager:
    def __init__(self, installation_id: int, user_token: str):
        self.installation_id = installation_id
        self.github_token = user_token
        self.installation_instance = app_models.GithubAppInstallation.objects.get(
            installation_id=self.installation_id
        )

        self.github_instance = github.Github(
            self.github_token,
        )
        self.github_manager_instance = lib.GithubInstallationManager(
            self.installation_id, self.github_token
        )

    def sync_repositories(self):
        repo_generator = self.github_manager_instance.get_repositories()
        for repo in repo_generator:
            app_models.GithubRepository.objects.get_or_create(
                repo_id=repo["id"],
                repo_name=repo["name"],
                repo_full_name=repo["full_name"],
                owner=self.installation_instance,
            )

    # a function called sync_open_prs which takes input the GithubRepository and syncs its open pull requests
    def sync_open_prs(self, repo: app_models.Repository):
        all_repo_ids = []
        for pr in self.github_instance.get_repo(repo.repo_full_name).get_pulls("open"):
            extra_data = {
                "pr_head_commit_sha": pr.head.sha,
                "pr_head_modified_on": pr.head.last_modified,
                "pr_head_commit_message": pr.head.label,
                "pr_title": pr.title,
                "pr_body": pr.body,
                "pr_state": pr.state,
                "pr_created_at": pr.created_at,
                "pr_updated_at": pr.updated_at,
                "pr_merged_at": pr.merged_at,
                "pr_closed_at": pr.closed_at,
                "pr_merged": pr.merged,
                "pr_owner_username": pr.user.login,
            }
            (instance, is_new) = app_models.GithubPullRequest.objects.update_or_create(
                pr_id=pr.id,
                pr_number=pr.number,
                repository=repo,
                defaults={**extra_data},
            )
            all_repo_ids.append(instance.id)
        return all_repo_ids


def get_active_token(social_account):
    last_token = social_account.socialtoken_set.last()
    if last_token.expires_at > timezone.now():
        return last_token
    social_app_instance = social_models.SocialApp.objects.get(
        provider=social_account.provider
    )
    extra = {
        "client_id": social_app_instance.client_id,
        "client_secret": social_app_instance.secret,
    }
    client = OAuth2Session(
        social_app_instance.client_id,
        token={
            "access_token": last_token.token,
            "refresh_token": last_token.token_secret,
            "token_type": "Bearer",
            "expires_in": "-30",  # initially 3600, need to be updated by you
        },
    )
    refresh_url = (
        "https://gitlab.com/oauth/token"
        if social_account.provider == "gitlab"
        else "https://github.com/login/oauth/access_token"
    )
    response = client.refresh_token(refresh_url, **extra)
    (token, _) = social_models.SocialToken.objects.update_or_create(
        app=last_token.app,
        account=last_token.account,
        defaults={
            "token": response["access_token"],
            "token_secret": response["refresh_token"],
            "expires_at": timezone.now()
            + datetime.timedelta(seconds=response["expires_in"]),
        },
    )
    return token
