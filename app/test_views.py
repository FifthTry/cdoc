from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase
import json
from . import views as app_views
from . import models as app_models
import mock
import requests_mock


class AuthCallbackTest(TestCase):
    # def setUp(self):
    #     self.user = Mock(id=123, email="foo@bar.com")

    #     patcher = patch("utils.requests.get")
    #     self.mock_response = Mock(status_code=200)
    #     self.mock_response.raise_for_status.return_value = None
    #     self.mock_response.json.return_value = {"UserId": self.user.id}
    #     self.mock_request = patcher.start()
    #     self.mock_request.return_value = self.mock_response

    # def tearDown(self):
    #     self.mock_request.stop()

    # def test_environment_set_in_context(self):
    #     self.assertIn("environment", context)

    # @mock.patch("requests.post", side_effect=mocked_requests_post)

    @requests_mock.Mocker()
    def test_get_future_assignments_with_multi_assignments(self, mocker):
        """
        Test for getting future assignments for a user with mocked API
        """
        mocker.register_uri(
            "POST", "https://github.com/login/oauth/access_token", json={"resp": 12}
        )
        # assignments = get_future_assignments(18888)
        request = RequestFactory().get(
            "/app/callback/?code=123&installation_id=456&setup_action=asd"
        )

        view = app_views.AuthCallback()
        view.setup(request)
        context = view.get(request)
        print(app_models.GithubUser.objects.all())
        # self.assertEqual(len(assignments), 2)
