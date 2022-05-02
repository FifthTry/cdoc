from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase
from django.contrib.sessions.middleware import SessionMiddleware
import json
from . import views as app_views
from . import models as app_models
import mock
import requests_mock
import lib


# def mocked_f2(**kargs):
#     return {
#         "Authorization": "token 1234567890",
#         "Accept": "application/vnd.github.machine-",
#     }


# class AuthCallbackTest(TestCase):
#     @mock.patch(
#         "lib.GithubInstallationManager.get_jwt_headers",
#         mocked_f2,
#     )
#     @requests_mock.Mocker()
#     def test_get_future_assignments_with_multi_assignments(self, mocker):
#         """
#         Test for getting future assignments for a user with mocked API
#         """
#         mocker.register_uri(
#             "POST",
#             "https://github.com/login/oauth/access_token",
#             text="access_token=access_token_value_1&expires_in=100&refresh_token=refresh_token_value&refresh_token_expires_in=3600",
#         )

#         mocker.register_uri(
#             "GET",
#             "https://api.github.com/app/installations/456",
#             json={
#                 "account": {
#                     "login": "test_organization",
#                     "id": 123456789,
#                     "type": "Organization",
#                     "avatar_url": "https://avatars3.githubusercontent.com/u/test_organization_avatar",
#                 }
#             },
#         )
#         response_user = object()
#         user_attrs = {
#             "login": "octocat",
#             "id": 1,
#             "node_id": "MDQ6VXNlcjE=",
#             "avatar_url": "https://github.com/images/error/octocat_happy.gif",
#             "gravatar_id": "",
#             "url": "https://api.github.com/users/octocat",
#             "html_url": "https://github.com/octocat",
#             "followers_url": "https://api.github.com/users/octocat/followers",
#             "following_url": "https://api.github.com/users/octocat/following{/other_user}",
#             "gists_url": "https://api.github.com/users/octocat/gists{/gist_id}",
#             "starred_url": "https://api.github.com/users/octocat/starred{/owner}{/repo}",
#             "subscriptions_url": "https://api.github.com/users/octocat/subscriptions",
#             "organizations_url": "https://api.github.com/users/octocat/orgs",
#             "repos_url": "https://api.github.com/users/octocat/repos",
#             "events_url": "https://api.github.com/users/octocat/events{/privacy}",
#             "received_events_url": "https://api.github.com/users/octocat/received_events",
#             "type": "User",
#             "site_admin": False,
#             "name": "monalisa octocat",
#             "company": "GitHub",
#             "blog": "https://github.com/blog",
#             "location": "San Francisco",
#             "email": "octocat@github.com",
#             "hireable": False,
#             "bio": "There once was...",
#             "twitter_username": "monatheoctocat",
#             "public_repos": 2,
#             "public_gists": 1,
#             "followers": 20,
#             "following": 0,
#             "created_at": "2008-01-14T04:33:35Z",
#             "updated_at": "2008-01-14T04:33:35Z",
#             "private_gists": 81,
#             "total_private_repos": 100,
#             "owned_private_repos": 100,
#             "disk_usage": 10000,
#             "collaborators": 8,
#             "two_factor_authentication": True,
#             "plan": {
#                 "name": "Medium",
#                 "space": 400,
#                 "private_repos": 20,
#                 "collaborators": 0,
#             },
#         }
#         mocker.register_uri(
#             "GET",
#             "https://api.github.com:443/user",
#             json=user_attrs,
#         )

#         mocker.register_uri(
#             "POST",
#             "https://api.github.com/app/installations/456/access_tokens",
#             json={
#                 "token": "access_token_value_1",
#                 "expires_at": "2020-01-14T04:33:35Z",
#             },
#         )
#         mocker.register_uri(
#             "GET",
#             "https://api.github.com/user/installations/456/repositories",
#             json={"repositories": [], "total_count": 0},
#         )
#         # assignments = get_future_assignments(18888)
#         request = RequestFactory().get(
#             "/app/callback/?code=123&installation_id=456&setup_action=asd"
#         )
#         middleware = SessionMiddleware(request)
#         middleware.process_request(request)
#         request.session.save()

#         view = app_views.AuthCallback()
#         view.setup(request)
#         context = view.get(request)
#         # print()
#         self.assertEqual(app_models.GithubUser.objects.count(), 1)
#         self.assertEqual(app_models.GithubRepository.objects.count(), 0)
#         self.assertEqual(app_models.GithubAppInstallation.objects.count(), 1)


# class TestGithubWebhook(TestCase):
#     @requests_mock.Mocker()
#     def test_repo_sync(self, mocker):
#         request = RequestFactory().post(
#             "/app/webhook-callback/",
#             data={"asd": 123},
#             content_type="application/json",
#             **{"HTTP_X-Github-Event": "pull_request"},
#         )
#         middleware = SessionMiddleware(request)
#         middleware.process_request(request)
#         request.session.save()

#         view = app_views.WebhookCallback()
#         view.setup(request)
#         context = view.post(request)
# print(context.body.decode("utf-8"))
