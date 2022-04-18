from . import models as app_models
import lib
import github


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
    def sync_open_prs(self, repo: app_models.GithubRepository):
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
