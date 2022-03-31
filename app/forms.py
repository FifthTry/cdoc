from django import forms
from . import models as app_models
import logging

logger = logging.getLogger(__name__)


class GithubPRApprovalForm(forms.ModelForm):
    class Meta:
        model = app_models.MonitoredPullRequest
        fields = ["pull_request_status", "documentation_pull_request"]

    def __init__(self, instance=None, *args, **kwargs):
        super().__init__(instance=instance, *args, **kwargs)
        if (
            instance.pull_request_status
            == app_models.MonitoredPullRequest.PullRequestStatus.NOT_CONNECTED
        ):
            self.fields.pop("pull_request_status")
            self.fields[
                "documentation_pull_request"
            ].queryset = app_models.GithubPullRequest.objects.filter(
                repository__in=instance.code_pull_request.repository.code_repos.all().values_list(
                    "documentation_repo", flat=True
                )
            )
        else:
            self.fields.pop("documentation_pull_request")
            self.fields.pop("pull_request_status")
            # print(self.fields["pull_request_status"].choices)
            # self.fields["pull_request_status"].initial = instance.pull_request_status

        #     self.fields[
        #         "documentation_pull_request"
        #     ].label = "Update the associated documentation PR"
        # # else:
        # if instance.documentation_pull_request is None:
        # self.fields["documentation_pull_request"] = doc_pr
        # logger.info(self.fields["documentation_pull_request"].__dict__)
