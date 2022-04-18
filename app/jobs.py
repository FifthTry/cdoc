import logging

import github
from . import lib as app_lib

from django_rq import job
from app import models as app_models

logger = logging.getLogger(__name__)


@job
def sync_repositories_for_installation(
    installation_instance: app_models.GithubAppInstallation,
):
    logger.info(f"GithubAppInstallation signal received for {installation_instance}")
    github_manager = app_lib.GithubDataManager(
        installation_instance.installation_id,
        installation_instance.creator.get_active_access_token(),
    )
    github_manager.sync_repositories()


@job
def test_job(a, b):
    assert False, a + b
