import gitlab
from app import lib as app_lib
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View
from app import models as app_models
from django.conf import settings
from requests.models import PreparedRequest
import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name="dispatch")
class WebhookCallback(View):
    def post(self, request, *args, **kwargs):
        headers = request.headers
        event_header = headers["X-Gitlab-Event"]
        request_body = json.loads(request.body.decode("utf-8"))
        gitlab_instance = gitlab.Gitlab(oauth_token=app_lib.get_active_token())
        if (
            event_header == "Merge Request Hook"
            and request_body["object_kind"] == "merge_request"
        ):
            project_name = request_body["request_body"]["path_with_namespace"]
            merge_request_id = request_body["object_attributes"]["iid"]
            app_models.PullRequest.objects.update_or_create(
                pr_number=merge_request_id,
                pr_id=request_body["object_attributes"]["id"],
                defaults={
                    
                }
            )
            pass
        assert False, (request.body, request.headers)
        pass
