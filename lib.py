import logging
import math
import uuid
from hmac import HMAC, compare_digest
from hashlib import sha256

import time
from typing import Tuple, Optional
import github
import datetime

import jwt
import requests
from cryptography.hazmat.backends import default_backend
from django.conf import settings
from app import models as app_models

logger = logging.getLogger(__name__)


class GithubInstallationManager:
    """
    This library contains the helper methods required while accessing github data.
    pyGithub is available but the installation access seems to be broken. So this
    util is a workaround"""

    def __init__(self, installation_id: int, user_token: str):
        self.installation_id = installation_id
        self.github_token = user_token

    @classmethod
    def get_jwt_headers(cls) -> dict:
        private_key = default_backend().load_pem_private_key(
            settings.APP_AUTH_KEY, None
        )
        time_since_epoch_in_seconds = int(time.time())
        payload = {
            # issued at time
            "iat": time_since_epoch_in_seconds,
            # JWT expiration time (10 minute maximum)
            "exp": time_since_epoch_in_seconds + (10 * 60),
            # GitHub App's identifier
            "iss": settings.GITHUB_CREDS["app_id"],
        }

        actual_jwt = jwt.encode(payload, private_key, algorithm="RS256")

        headers = {
            "Authorization": "Bearer {}".format(actual_jwt),
            "Accept": "application/vnd.github.machine-man-preview+json",
        }
        return headers

    def get_installation_access_token(self) -> Tuple[str, datetime.datetime]:
        headers = GithubInstallationManager.get_jwt_headers()
        headers.update({"Accept": "application/vnd.github.v3+json"})
        response = requests.post(
            f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
            headers=headers,
        )
        if response.ok:
            response_data = response.json()
            logger.info(response_data)
            try:
                return (
                    response_data["token"],
                    datetime.datetime.strptime(
                        response_data["expires_at"], "%Y-%m-%dT%H:%M:%S%z"
                    ),
                )
            except KeyError as e:
                logger.error(
                    f"Unable to get the access_token for installation_id={self.installation_id}, {response_data}"
                )
        else:
            logger.error(
                f"Unable to communicate with github {response.content.decode()}",
            )

    def get_installation_details(self):
        headers = GithubInstallationManager.get_jwt_headers()
        headers.update({"Accept": "application/vnd.github.v3+json"})
        response = requests.get(
            f"https://api.github.com/app/installations/{self.installation_id}",
            headers=headers,
        )
        if response.ok:
            response_data = response.json()
            logger.info(response.content.decode())
            try:
                return response_data
            except KeyError as e:
                logger.error(
                    f"Unable to get the access_token for installation_id={self.installation_id}, {response_data}"
                )
        else:
            logger.error(
                f"Unable to communicate with github {response.content.decode()}",
            )

    def _get_repository_page(self, page: int, per_page: Optional[int] = None):
        headers = GithubInstallationManager.get_jwt_headers()
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Token {self.github_token}",
        }
        response = requests.get(
            f"https://api.github.com/user/installations/{self.installation_id}/repositories?per_page={per_page}&page={page}",
            headers=headers,
        )
        if response.ok:
            response_data = response.json()
            logger.info(response.content.decode())
            return response_data
        else:
            logger.error(
                f"Unable to communicate with github {response.content.decode()}",
            )

    # a function to take the installation id and githubToken and return the repositories for the installation
    def get_repositories(self, max_count: Optional[int] = math.inf):
        per_page = 30
        if max_count is not None:
            per_page = min(max_count, per_page)
        current_page = 1
        response = self._get_repository_page(current_page, per_page)
        for repo in response["repositories"]:
            yield repo
        for page_no in range(
            2, math.ceil(min(response["total_count"], max_count) / per_page) + 1
        ):
            response = self._get_repository_page(page_no, per_page)
            for repo in response["repositories"]:
                yield repo


def verify_signature(github_signature_256, request_body, secret_string):
    received_sign = (
        github_signature_256.split("sha256=")[-1].strip()
    )
    secret = secret_string.encode()
    expected_sign = HMAC(key=secret, msg=request_body, digestmod=sha256).hexdigest()
    return compare_digest(received_sign, expected_sign)
