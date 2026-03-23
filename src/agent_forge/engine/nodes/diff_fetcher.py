"""Diff fetcher node — retrieves PR diff from GitHub."""

import logging
from dataclasses import asdict

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.github.client import GitHubClient

logger = logging.getLogger(__name__)

# Mock data fallback — PR #482: Add retry logic to PaymentService
MOCK_PR_DIFF = {
    "pr_number": 482,
    "title": "Add retry logic to PaymentService",
    "author": "rohit",
    "base_ref": "main",
    "head_ref": "feature/payment-retry",
    "description": (
        "Added retry mechanism with exponential backoff for transient payment "
        "failures (5xx responses). New RetryConfig class with configurable max "
        "retries (3), initial delay (1s), and backoff multiplier (2x)."
    ),
    "files": [
        {
            "path": "src/main/java/com/app/service/PaymentService.java",
            "status": "modified",
            "language": "java",
            "lines_added": 67,
            "lines_deleted": 3,
            "lines_modified": 12,
            "patch": "@@ -45,6 +45,73 @@\n public class PaymentService {\n+    ...",
        },
        {
            "path": "src/main/java/com/app/config/RetryConfig.java",
            "status": "added",
            "language": "java",
            "lines_added": 34,
            "lines_deleted": 0,
            "lines_modified": 0,
            "patch": "@@ -0,0 +1,34 @@\n+package com.app.config;...",
        },
    ],
}


def _serialize_file_change(fc) -> dict:
    """Convert a FileChange dataclass to a serializable dict."""
    return {
        "path": fc.path,
        "status": fc.status.value if hasattr(fc.status, "value") else str(fc.status),
        "language": fc.language.value if hasattr(fc.language, "value") else str(fc.language),
        "old_path": fc.old_path,
        "lines_added": fc.lines_added,
        "lines_deleted": fc.lines_deleted,
        "lines_modified": fc.lines_modified,
        "patch": fc.patch,
        "hunks": [
            {
                "old_start": h.old_start,
                "old_count": h.old_count,
                "new_start": h.new_start,
                "new_count": h.new_count,
                "added_lines": h.added_lines,
                "removed_lines": h.removed_lines,
            }
            for h in fc.hunks
        ],
    }


def _serialize_pr_diff(pr_diff) -> dict:
    """Convert a PRDiff dataclass to a serializable dict."""
    return {
        "pr_number": pr_diff.pr_number,
        "title": pr_diff.title,
        "author": pr_diff.author,
        "base_ref": pr_diff.base_ref,
        "head_ref": pr_diff.head_ref,
        "description": pr_diff.description,
        "files": [_serialize_file_change(f) for f in pr_diff.files],
    }


async def diff_fetcher_node(state: AgentState) -> dict:
    """Fetch PR diff from GitHub. Falls back to mock data if GitHub fails."""
    pr_number = state["pr_number"]
    repo = state["repo"]

    logger.info(f"Fetching diff for {repo} PR #{pr_number}")

    # Try real GitHub API
    try:
        settings = get_settings()
        client = GitHubClient(github_token=settings.github_token)

        # Parse owner/repo
        parts = repo.split("/")
        if len(parts) == 2:
            owner, repo_name = parts
        else:
            raise ValueError(f"Invalid repo format: {repo}. Expected owner/repo")

        pr_diff = await client.get_pr_diff(owner, repo_name, pr_number)

        diff_dict = _serialize_pr_diff(pr_diff)
        changed_files = [f["path"] for f in diff_dict["files"]]

        logger.info(f"Fetched real PR diff: {len(changed_files)} files changed")

        return {
            "current_step": "diff_fetcher",
            "pr_diff": diff_dict,
            "changed_files": changed_files,
        }

    except Exception as e:
        logger.warning(f"GitHub API failed ({e}), falling back to mock data")

        diff = MOCK_PR_DIFF.copy()
        diff["pr_number"] = pr_number
        changed_files = [f["path"] for f in diff["files"]]

        return {
            "current_step": "diff_fetcher",
            "pr_diff": diff,
            "changed_files": changed_files,
        }
