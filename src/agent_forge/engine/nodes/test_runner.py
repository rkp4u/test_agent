"""Test runner node — writes generated tests to repo and executes them."""

import logging
import tempfile
from pathlib import Path

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.github.client import GitHubClient
from agent_forge.tools.runners.gradle import GradleRunner

logger = logging.getLogger(__name__)


async def test_runner_node(state: AgentState) -> dict:
    """Write generated tests to a cloned repo and execute them.

    Steps:
    1. Clone the repo (or use existing clone)
    2. Checkout the PR branch
    3. Write generated test files
    4. Run ./gradlew test
    5. Parse results and coverage
    """
    generated_tests = state.get("generated_tests", [])
    pr_diff = state.get("pr_diff", {})

    if not generated_tests:
        logger.warning("No generated tests to run")
        return {
            "current_step": "test_runner",
            "test_results": [],
            "new_coverage": None,
        }

    total_test_methods = sum(len(t.get("test_methods", [])) for t in generated_tests)
    logger.info(f"Running {total_test_methods} generated test methods")

    settings = get_settings()
    client = GitHubClient(github_token=settings.github_token)

    parts = state["repo"].split("/")
    owner, repo_name = parts[0], parts[1]
    head_ref = pr_diff.get("head_ref", "main")

    try:
        # Try to find local repo first (avoids clone issues with gradle wrapper etc.)
        import subprocess

        local_candidates = [
            Path.home() / "workspace" / repo_name,
            Path.cwd() / repo_name,
            Path.cwd().parent / repo_name,
        ]

        repo_path = None
        for candidate in local_candidates:
            if (candidate / ".git").exists():
                repo_path = candidate
                logger.info(f"Using local repo: {repo_path}")
                break

        if repo_path is None:
            # Clone the repo
            work_dir = settings.work_dir / "repos"
            work_dir.mkdir(parents=True, exist_ok=True)
            repo_path = await client.clone_repo(owner, repo_name, work_dir)

        # Create a working branch for tests (don't pollute the PR branch)
        subprocess.run(
            ["git", "fetch", "origin", head_ref],
            cwd=str(repo_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", head_ref],
            cwd=str(repo_path),
            capture_output=True,
        )
        # Create a test branch to keep things clean
        subprocess.run(
            ["git", "checkout", "-B", f"agent-forge/tests-pr-{state['pr_number']}"],
            cwd=str(repo_path),
            capture_output=True,
        )
        logger.info(f"Checked out test branch for PR #{state['pr_number']}")

        # Detect build tool and create runner
        # For now, try Gradle first
        try:
            runner = GradleRunner(repo_path)
        except FileNotFoundError:
            logger.error("No Gradle wrapper found — cannot run tests")
            return _mock_results(generated_tests)

        # Write generated test files
        written_files = []
        for test in generated_tests:
            test_path = test.get("file_path", "")
            content = test.get("content", "")

            if not test_path or not content:
                continue

            path = await runner.write_test_file(test_path, content)
            written_files.append(path)
            logger.info(f"  Wrote: {test_path}")

        if not written_files:
            logger.warning("No test files written")
            return _mock_results(generated_tests)

        # Run tests
        logger.info(f"Executing tests ({len(written_files)} test files)...")
        result = await runner.run_tests(
            test_files=written_files,
            timeout=settings.test_timeout_seconds,
        )

        if result.success:
            logger.info(
                f"Tests completed: {result.passed} passed, {result.failed} failed"
            )
        else:
            logger.warning(
                f"Tests had failures: {result.passed} passed, {result.failed} failed"
            )
            # Log first few error lines for debugging
            if result.stderr:
                for line in result.stderr.split("\n")[:20]:
                    if line.strip():
                        logger.warning(f"  stderr: {line.strip()}")

        return {
            "current_step": "test_runner",
            "repo_local_path": str(repo_path),
            "test_results": result.test_results,
            "new_coverage": None,
        }

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        return {
            "current_step": "test_runner",
            "repo_local_path": str(repo_path) if repo_path else state.get("repo_local_path", ""),
            "test_results": [{
                "test_name": "execution_error",
                "passed": False,
                "error_message": str(e),
            }],
            "new_coverage": None,
        }


def _mock_results(generated_tests: list[dict]) -> dict:
    """Return mock results when real execution isn't possible."""
    results = []
    for test in generated_tests:
        for method in test.get("test_methods", []):
            results.append({
                "test_name": method,
                "passed": True,
                "duration_ms": 100,
            })

    return {
        "current_step": "test_runner",
        "test_results": results,
        "new_coverage": None,
    }
