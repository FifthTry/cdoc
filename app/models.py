import datetime
import enum
import logging
import uuid
from urllib.parse import parse_qs

import lib
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Token(models.Model):
    """
    This model takes care of the tokens generated by the Github applications.
    """

    token = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        abstract = True


class GithubUser(models.Model):
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="github_user")
    account_name = models.CharField(max_length=200)
    account_id = models.BigIntegerField()
    account_type = models.CharField(max_length=20)
    avatar_url = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def access_token(self):
        try:
            return self.access_tokens.exclude(expires_at__lt=timezone.now()).latest("expires_at").token
        except:
            return None

    @property
    def refresh_token(self):
        try:
            return self.refresh_tokens.exclude(expires_at__lt=timezone.now()).latest("expires_at").token
        except:
            return None

    def process_token_response(self, token_response):
        now = timezone.now()
        logger.info(token_response)
        data = parse_qs(token_response)
        GithubUserAccessToken.objects.create(
            token=data["access_token"][0],
            github_user=self,
            expires_at=now +
            datetime.timedelta(seconds=int(data["expires_in"][0]))
        )
        GithubUserRefreshToken.objects.create(
            token=data["refresh_token"][0],
            github_user=self,
            expires_at=now +
            datetime.timedelta(
                seconds=int(data["refresh_token_expires_in"][0]))
        )

    def get_new_tokens(self):
        refresh_token = self.refresh_tokens.exclude(
            expires_at__lt=timezone.now()).latest("expires_at")
        response = requests.post("https://github.com/login/oauth/access_token", data={
            "refresh_token": refresh_token.token,
            "grant_type": "refresh_token",
            "client_id": settings.GITHUB_CREDS['client_id'],
            "client_secret": settings.GITHUB_CREDS['client_secret'],
        })
        self.process_token_response(response.content.decode())


class GithubUserAccessToken(Token):
    github_user = models.ForeignKey(
        GithubUser, on_delete=models.CASCADE, related_name="access_tokens")


class GithubUserRefreshToken(Token):
    github_user = models.ForeignKey(
        GithubUser, on_delete=models.CASCADE, related_name="refresh_tokens")


class GithubAppInstallation(models.Model):
    """
    This model takes care of the Github installations.
    """

    class InstallationState(models.TextChoices):
        INSTALLED = "INSTALLED", "Installed"
        UNINSTALLED = "UNINSTALLED", "Uninstalled"

    installation_id = models.BigIntegerField(unique=True, db_index=True)
    creator = models.ForeignKey(GithubUser, on_delete=models.PROTECT)
    state = models.CharField(
        max_length=20, choices=InstallationState.choices)
    account_name = models.CharField(max_length=200)
    account_id = models.BigIntegerField()
    account_type = models.CharField(max_length=20)
    avatar_url = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.account_name}[{self.installation_id}] Owner: {self.creator.account_name}"

    @property
    def access_token(self):
        try:
            return self.tokens.exclude(expires_at__lte=timezone.now()).latest('created_at').token
        except GithubInstallationToken.DoesNotExist:
            self.update_token()
            return self.get_latest_active_token()

    def update_token(self):
        """
        Fetches the latest access token for the installation. Returns true/false depending on whether 
        the requested token has been updated
        """
        # User token not required for this step
        github_installation_manager = lib.GithubInstallationManager(
            installation_id=self.installation_id, user_token="")
        token, expires_at = github_installation_manager.get_installation_access_token()
        return GithubInstallationToken.objects.get_or_create(
            token=token,
            expires_at=expires_at,
            github_app_installation=self,
        )[1]


class GithubInstallationToken(Token):
    github_app_installation = models.ForeignKey(
        GithubAppInstallation, on_delete=models.CASCADE, related_name="tokens"
    )


class GithubRepository(models.Model):
    repo_id = models.BigIntegerField()
    repo_name = models.CharField(max_length=150)
    repo_full_name = models.CharField(max_length=200)
    owner = models.ForeignKey(GithubAppInstallation, on_delete=models.PROTECT)

    def __str__(self) -> str:
        return self.repo_full_name


class GithubRepoMap(models.Model):

    class IntegrationType(models.TextChoices):
        """
            FULL integration restricts the PRs to process only after the related PR is merged
            PARTIAL check is not restrictive
        """
        FULL = "FULL", "Full"
        PARTIAL = "PARTIAL", "Partial"
    integration = models.ForeignKey(
        GithubAppInstallation, on_delete=models.PROTECT
    )
    code_repo = models.ForeignKey(
        GithubRepository, on_delete=models.PROTECT, related_name="code_repos")
    documentation_repo = models.ForeignKey(
        GithubRepository, on_delete=models.PROTECT, related_name="documentation_repos")
    integration_type = models.CharField(
        max_length=20, choices=IntegrationType.choices)


class GithubPullRequestBase(models.Model):
    pr_id = models.BigIntegerField()
    pr_number = models.BigIntegerField()
    head_commit_sha = models.CharField(max_length=40)
    head_tree_sha = models.CharField(max_length=40)
    head_modified_on = models.DateTimeField()
    head_commit_message = models.CharField(max_length=200)

    class Meta:
        abstract = True


class DocumentationRepoPullRequest(GithubPullRequestBase):
    repository = models.ForeignKey(
        GithubRepository, on_delete=models.CASCADE, related_name="doc_repo_prs")
    # To be set programatically when the PR is approved
    is_approved = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.repository.full_name}[{self.pr_number}] {self.is_approved}"


class GithubCheckRun(models.Model):
    run_id = models.BigIntegerField(blank=True, null=True)
    unique_id = models.UUIDField(default=uuid.uuid4)
    # Head of the request when it was run
    head_sha = models.CharField(max_length=40)
    pull_request = models.ForeignKey(
        "CodeRepoPullRequest", on_delete=models.PROTECT, related_name="checks")
    # This flag will be set to true if:
    # 1. The documentation_pr exists and pr has been approved(i.e. webhook for approval received)
    # 2. The documentation_pr does not exist and the user sets it manually
    force_approve = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        unique_together = ('head_sha', "pull_request", )

    def save(self, *args, **kwargs):
        if not self.pk:
            # PK doesn't exist, new instance being saved to the DB. Create a new check
            # requests.post()
            # Get the token of the creator from the tree
            # token = self.pull_request.repository.owner.creator.access_token
            # headers = {
            #     "Accept": "application/vnd.github.v3+json",
            #     "Authorization": f"Token {token}"
            # }
            # data = {
            #     "name": "continuous documentation",
            #     "head_sha": self.head_sha,
            #     "external_id": self.unique_id,
            #     "status": "in_progress",
            # }
            # response = requests.post(
            #     f"https://api.github.com/repos/{self.pull_request.repository.repo_full_name}/check-runs", headers=headers, json=data)
            pass
        super().save(*args, **kwargs)


# class GithubCheckLog(models.Model):
#     check = models.ForeignKey(GithubCheckRun, on_delete=models.CASCADE)
#     pass


class CodeRepoPullRequest(GithubPullRequestBase):
    repository = models.ForeignKey(
        GithubRepository, on_delete=models.CASCADE, related_name="code_repo_prs")
    documentation_pr = models.ForeignKey(
        DocumentationRepoPullRequest, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.repository.repo_full_name}[{self.pr_number}]"

    def evaluate_check(self):
        try:
            latest_check = self.checks.get(head_sha=self.head_commit_sha)
        except GithubCheckRun.DoesNotExist:
            # Check doesn't exist, create a new check
            GithubCheckRun.objects.create(
                repository=self,
                head_sha=self.head_commit_sha,
            )
