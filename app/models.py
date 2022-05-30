import datetime
from email.policy import default
import enum
import logging
import uuid
from urllib.parse import parse_qs
import github
import lib
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from allauth.socialaccount import models as social_models

logger = logging.getLogger(__name__)


class AppInstallation(models.Model):
    """
    This model takes care of the Github installations.
    """

    class InstallationState(models.TextChoices):
        INSTALLED = "INSTALLED", "Installed"
        UNINSTALLED = "UNINSTALLED", "Uninstalled"
        SUSPENDED = "SUSPENDED", "Suspended"

    social_app = models.ForeignKey(social_models.SocialApp, on_delete=models.PROTECT)
    installation_id = models.BigIntegerField(unique=True, db_index=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.PROTECT)
    state = models.CharField(max_length=20, choices=InstallationState.choices)
    account_name = models.CharField(max_length=200)
    account_id = models.BigIntegerField()
    account_type = models.CharField(max_length=20)
    avatar_url = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("social_app", "installation_id")

    def __str__(self) -> str:
        return f"{self.account_name}[{self.installation_id}] Owner: {self.creator.username}"


class AppUser(models.Model):
    installation = models.ForeignKey(AppInstallation, on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("installation", "user")


class Repository(models.Model):
    repo_id = models.BigIntegerField()
    repo_name = models.CharField(max_length=150)
    repo_full_name = models.CharField(max_length=200)
    app = models.ForeignKey(social_models.SocialApp, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("repo_id", "app")

    def __str__(self) -> str:
        return self.repo_full_name

    def pulls_page_url(self):
        return f"/{self.app.provider}/{self.repo_full_name}/pulls/"


class UserRepoAccess(models.Model):
    class AccessLevel(models.TextChoices):
        OWNER = 50, "Owner"
        MAINTAINER = 40, "Maintainer"
        DEVELOPER = 30, "Developer"
        REPORTER = 20, "Reporter"
        GUEST = 10, "Guest"
        MINIMAL = 5, "Minimal"
        NO_ACCESS = 0, "No Access"

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    social_account = models.ForeignKey(
        social_models.SocialAccount, on_delete=models.CASCADE
    )
    access = models.IntegerField(choices=AccessLevel.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("repository", "social_account")


class MonitoredRepositoryMap(models.Model):
    class IntegrationType(models.TextChoices):
        """
        FULL integration restricts the PRs to process only after the related PR is merged
        PARTIAL check is not restrictive
        """

        FULL = "FULL", "Full"
        PARTIAL = "PARTIAL", "Partial"

    # integration = models.ForeignKey(AppInstallation, on_delete=models.PROTECT)
    code_repo = models.ForeignKey(
        Repository, on_delete=models.PROTECT, related_name="code_repos"
    )
    documentation_repo = models.ForeignKey(
        Repository, on_delete=models.PROTECT, related_name="documentation_repos"
    )
    integration_type = models.CharField(max_length=20, choices=IntegrationType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("code_repo", "documentation_repo")


class PullRequest(models.Model):
    pr_id = models.BigIntegerField()
    pr_number = models.BigIntegerField()
    pr_head_commit_sha = models.CharField(max_length=40)
    pr_head_modified_on = models.DateTimeField(null=True, blank=True)
    pr_head_commit_message = models.CharField(max_length=200)
    pr_title = models.CharField(max_length=200)
    pr_body = models.TextField(default="", blank=True, null=True)
    pr_state = models.CharField(max_length=20)
    pr_created_at = models.DateTimeField(null=True, blank=True)
    pr_updated_at = models.DateTimeField(null=True, blank=True)
    pr_merged_at = models.DateTimeField(null=True, blank=True)
    pr_closed_at = models.DateTimeField(null=True, blank=True)
    pr_merged = models.BooleanField(default=False)
    pr_owner_username = models.CharField(max_length=100)
    updated_on = models.DateTimeField(auto_now=True)
    repository = models.ForeignKey(Repository, on_delete=models.PROTECT)

    def __str__(self) -> str:
        return f"{self.repository.repo_full_name}/{self.pr_number} @ {self.pr_head_commit_sha[:7]}"

    def get_url(self):
        return (
            f"https://github.com/{self.repository.repo_full_name}/pull/{self.pr_number}"
        )


class MonitoredPullRequest(models.Model):
    class PullRequestStatus(models.TextChoices):
        """
        NOT_CONNECTED: Documentation PR Not connected
        APPROVAL_PENDING: PR Document is connected but the documentation is approved
        STALE_CODE: Documentation is connected but the Documentation has updated since the last commit
        STALE_APPROVAL: Approved in the past but the code has diverged since then
        APPROVED: Approved and the documentation is up to date
        """

        NOT_CONNECTED = "NOT_CONNECTED", "Not Connected"
        APPROVAL_PENDING = "APPROVAL_PENDING", "Approval Pending"
        STALE_CODE = "STALE_CODE", "Stale Code"
        STALE_APPROVAL = "STALE_APPROVAL", "Stale Approval"
        APPROVED = "APPROVED", "Approved"
        MANUAL_APPROVAL = "MANUALLY_APPROVED", "Manual Approval"

    code_pull_request = models.OneToOneField(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="monitored_code",
    )
    documentation_pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="monitored_documentation",
    )
    pull_request_status = models.CharField(
        max_length=20,
        choices=PullRequestStatus.choices,
        default=PullRequestStatus.NOT_CONNECTED,
    )
    # integration = models.ForeignKey(AppInstallation, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("code_pull_request", "documentation_pull_request")

    def __str__(self) -> str:
        return f"{self.code_pull_request.repository.repo_full_name}[{self.code_pull_request.pr_number}]"

    def save(self, *args, **kwargs):
        if (
            self.documentation_pull_request is not None
            and self.pull_request_status
            == MonitoredPullRequest.PullRequestStatus.NOT_CONNECTED
        ):
            self.pull_request_status = (
                MonitoredPullRequest.PullRequestStatus.APPROVAL_PENDING
            )
        elif (
            self.documentation_pull_request is None
            and self.pull_request_status
            != MonitoredPullRequest.PullRequestStatus.MANUAL_APPROVAL
            # In case of a manual approval, the documentation PR is not connected
        ):
            self.pull_request_status = (
                MonitoredPullRequest.PullRequestStatus.NOT_CONNECTED
            )
        return super().save(*args, **kwargs)

    def get_display_name(self):
        return f"{self.code_pull_request.repository.repo_full_name}/#{self.code_pull_request.pr_number}: {self.code_pull_request.pr_title}"

    @property
    def is_approved(self):
        return self.pull_request_status in [
            MonitoredPullRequest.PullRequestStatus.APPROVED,
            MonitoredPullRequest.PullRequestStatus.MANUAL_APPROVAL,
        ]

    def get_latest_approval(self):
        try:
            return self.prapproval_set.latest("created_on")
        except:
            return None


class PrApproval(models.Model):
    updated_on = models.DateTimeField(auto_now=True)
    created_on = models.DateTimeField(auto_now_add=True)
    monitored_pull_request = models.ForeignKey(
        MonitoredPullRequest, on_delete=models.CASCADE
    )
    approver = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class PullRequestCheck(models.Model):
    run_id = models.BigIntegerField(blank=True, null=True)
    unique_id = models.UUIDField(default=uuid.uuid4)
    # Head of the request when it was run
    run_sha = models.CharField(max_length=40)
    ref_pull_request = models.ForeignKey(
        MonitoredPullRequest, on_delete=models.PROTECT, related_name="checks"
    )
    # This flag will be set to true if:
    # 1. The documentation_pr exists and pr has been approved(i.e. webhook for approval received)
    # 2. The documentation_pr does not exist and the user sets it manually
    force_approve = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        unique_together = (
            "run_sha",
            "ref_pull_request",
        )

    def __str__(self):
        return f"{self.ref_pull_request.code_pull_request.repository.repo_full_name}/{self.ref_pull_request.code_pull_request.pr_number} @ {self.run_sha[:7]} [{self.force_approve}]"

    def save(self, *args, **kwargs):

        if not self.pk:
            # PK doesn't exist, new instance being saved to the DB. Create a new check
            token = (
                self.ref_pull_request.code_pull_request.repository.owner.creator.access_token
            )
            github_app_instance = github.Github(token)
            github_repo = github_app_instance.get_repo(
                self.ref_pull_request.code_pull_request.repository.repo_id
            )
            check_run_instance = github_repo.create_check_run(
                name="Continuous Documentation",
                head_sha=self.run_sha,
                external_id=self.unique_id.__str__(),
                status="in_progress",
                details_url=f"{settings.WEBSITE_HOST}/{github_repo.full_name}/pull/{self.ref_pull_request.code_pull_request.pr_number}",
            )
            logger.info(
                "Created new check run for PR", extra={"response": check_run_instance}
            )
            self.run_id = check_run_instance.id
        super().save(*args, **kwargs)


class GithubMarketplaceEvent(models.Model):
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
