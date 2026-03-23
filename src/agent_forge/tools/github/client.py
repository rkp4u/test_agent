"""GitHub client — gh CLI primary, PyGithub fallback."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

from agent_forge.models.enums import FileChangeStatus, Language
from agent_forge.tools.github.models import FileChange, Hunk, PRDiff

logger = logging.getLogger(__name__)


class GitHubClient:
    """Fetches PR data from GitHub.

    Uses gh CLI as the primary method (no tokens stored in code).
    Falls back to PyGithub if gh CLI is unavailable.
    """

    def __init__(self, github_token: str = ""):
        self._gh_available = shutil.which("gh") is not None
        self._token = github_token

        if self._gh_available:
            logger.info("Using gh CLI for GitHub operations")
        elif self._token:
            logger.info("Using PyGithub for GitHub operations")
        else:
            logger.warning("No GitHub auth available — gh CLI not found and no token provided")

    async def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        """Get PR metadata (title, author, branches, description)."""
        if self._gh_available:
            return self._gh_pr_info(owner, repo, pr_number)
        return self._pygithub_pr_info(owner, repo, pr_number)

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> PRDiff:
        """Get full PR diff with parsed file changes."""
        # Get PR metadata
        pr_info = await self.get_pr_info(owner, repo, pr_number)

        # Get file changes with patches
        if self._gh_available:
            files = self._gh_pr_files(owner, repo, pr_number)
        else:
            files = self._pygithub_pr_files(owner, repo, pr_number)

        return PRDiff(
            pr_number=pr_number,
            title=pr_info.get("title", ""),
            author=pr_info.get("author", ""),
            base_ref=pr_info.get("base_ref", "main"),
            head_ref=pr_info.get("head_ref", ""),
            description=pr_info.get("body", ""),
            files=files,
        )

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Get file content at a specific git ref."""
        if self._gh_available:
            return self._gh_file_content(owner, repo, path, ref)
        return self._pygithub_file_content(owner, repo, path, ref)

    async def clone_repo(self, owner: str, repo: str, target_dir: Path) -> Path:
        """Clone a repo to a local directory."""
        repo_url = f"https://github.com/{owner}/{repo}.git"
        repo_dir = target_dir / repo

        if repo_dir.exists():
            logger.info(f"Repo already cloned at {repo_dir}")
            return repo_dir

        result = subprocess.run(
            ["git", "clone", repo_url, str(repo_dir)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        logger.info(f"Cloned {owner}/{repo} to {repo_dir}")
        return repo_dir

    # --- gh CLI methods ---

    def _gh_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        """Get PR info via gh CLI."""
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{pr_number}",
                "--jq", '{ title: .title, author: .user.login, '
                        'base_ref: .base.ref, head_ref: .head.ref, '
                        'body: .body, state: .state }',
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"gh api failed: {result.stderr}")

        return json.loads(result.stdout)

    def _gh_pr_files(self, owner: str, repo: str, pr_number: int) -> list[FileChange]:
        """Get PR file changes via gh CLI."""
        # Get file list with stats
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{pr_number}/files",
                "--paginate",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"gh api failed: {result.stderr}")

        files_data = json.loads(result.stdout)
        file_changes = []

        for f in files_data:
            path = f.get("filename", "")
            ext = Path(path).suffix
            status_map = {
                "added": FileChangeStatus.ADDED,
                "modified": FileChangeStatus.MODIFIED,
                "removed": FileChangeStatus.DELETED,
                "renamed": FileChangeStatus.RENAMED,
            }

            fc = FileChange(
                path=path,
                status=status_map.get(f.get("status", ""), FileChangeStatus.MODIFIED),
                language=Language.from_extension(ext),
                old_path=f.get("previous_filename"),
                lines_added=f.get("additions", 0),
                lines_deleted=f.get("deletions", 0),
                patch=f.get("patch", ""),
            )

            # Parse the patch into hunks
            if fc.patch:
                fc.hunks = _parse_patch(fc.patch)

            file_changes.append(fc)

        return file_changes

    def _gh_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Get file content via gh CLI."""
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/contents/{path}",
                "-H", "Accept: application/vnd.github.raw+json",
                "--method", "GET",
                "-f", f"ref={ref}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"gh api failed for {path}@{ref}: {result.stderr}")

        return result.stdout

    # --- PyGithub fallback methods ---

    def _pygithub_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        from github import Github

        g = Github(self._token)
        pr = g.get_repo(f"{owner}/{repo}").get_pull(pr_number)
        return {
            "title": pr.title,
            "author": pr.user.login,
            "base_ref": pr.base.ref,
            "head_ref": pr.head.ref,
            "body": pr.body or "",
            "state": pr.state,
        }

    def _pygithub_pr_files(self, owner: str, repo: str, pr_number: int) -> list[FileChange]:
        from github import Github

        g = Github(self._token)
        pr = g.get_repo(f"{owner}/{repo}").get_pull(pr_number)
        file_changes = []

        for f in pr.get_files():
            ext = Path(f.filename).suffix
            status_map = {
                "added": FileChangeStatus.ADDED,
                "modified": FileChangeStatus.MODIFIED,
                "removed": FileChangeStatus.DELETED,
                "renamed": FileChangeStatus.RENAMED,
            }

            fc = FileChange(
                path=f.filename,
                status=status_map.get(f.status, FileChangeStatus.MODIFIED),
                language=Language.from_extension(ext),
                old_path=f.previous_filename,
                lines_added=f.additions,
                lines_deleted=f.deletions,
                patch=f.patch or "",
            )

            if fc.patch:
                fc.hunks = _parse_patch(fc.patch)

            file_changes.append(fc)

        return file_changes

    def _pygithub_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        from github import Github

        g = Github(self._token)
        content = g.get_repo(f"{owner}/{repo}").get_contents(path, ref=ref)
        return content.decoded_content.decode("utf-8")


def _parse_patch(patch: str) -> list[Hunk]:
    """Parse a unified diff patch string into Hunk objects."""
    hunks = []
    current_hunk = None
    old_line = 0
    new_line = 0

    for line in patch.split("\n"):
        if line.startswith("@@"):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            if current_hunk:
                hunks.append(current_hunk)

            try:
                parts = line.split("@@")[1].strip()
                old_part, new_part = parts.split(" ")
                old_start = int(old_part.split(",")[0].lstrip("-"))
                old_count = int(old_part.split(",")[1]) if "," in old_part else 1
                new_start = int(new_part.split(",")[0].lstrip("+"))
                new_count = int(new_part.split(",")[1]) if "," in new_part else 1
            except (ValueError, IndexError):
                old_start, old_count, new_start, new_count = 0, 0, 0, 0

            current_hunk = Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
            )
            old_line = old_start
            new_line = new_start

        elif current_hunk is not None:
            if line.startswith("+"):
                current_hunk.added_lines.append((new_line, line[1:]))
                new_line += 1
            elif line.startswith("-"):
                current_hunk.removed_lines.append((old_line, line[1:]))
                old_line += 1
            else:
                # Context line
                content = line[1:] if line.startswith(" ") else line
                current_hunk.context_lines.append((new_line, content))
                old_line += 1
                new_line += 1

    if current_hunk:
        hunks.append(current_hunk)

    return hunks
