"""Coverage checker node — detects build tool and reports existing test coverage status."""

import logging

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.coverage.detector import detect_build_tool
from agent_forge.tools.github.client import GitHubClient

logger = logging.getLogger(__name__)


async def coverage_checker_node(state: AgentState) -> dict:
    """Check existing test coverage configuration and status.

    In Phase 3, this:
    1. Detects the build tool (Gradle/Maven/pip)
    2. Checks if JaCoCo/coverage is configured
    3. Looks for existing test files
    4. Reports coverage status (actual coverage parsing requires cloning + building)
    """
    pr_diff = state.get("pr_diff", {})
    changed_files = state.get("changed_files", [])

    if not pr_diff:
        return {
            "current_step": "coverage_checker",
            "existing_coverage": _empty_coverage(),
        }

    settings = get_settings()
    client = GitHubClient(github_token=settings.github_token)

    parts = state["repo"].split("/")
    owner, repo_name = parts[0], parts[1]
    head_ref = pr_diff.get("head_ref", "main")

    # Detect build tool and coverage configuration
    build_info = await detect_build_tool(client, owner, repo_name, head_ref)

    logger.info(
        f"Build tool: {build_info['build_tool'].value}, "
        f"Test framework: {build_info['test_framework'].value}, "
        f"Coverage configured: {build_info['has_coverage']}"
    )

    # Check for existing test files matching changed source files
    existing_test_files = await _find_existing_tests(
        client, owner, repo_name, head_ref, changed_files, build_info
    )

    # Build coverage status report
    # Note: Actual line-level coverage requires cloning and running tests locally (Phase 4)
    # For now, we report structural coverage: which files have tests and which don't
    files_coverage = {}
    for file_path in changed_files:
        has_test = file_path in existing_test_files
        test_file = existing_test_files.get(file_path)

        files_coverage[file_path] = {
            "file_path": file_path,
            "has_test_file": has_test,
            "test_file": test_file,
            "line_rate": 0.0,  # Phase 4: real JaCoCo data
            "branch_rate": 0.0,
            "status": "partially_covered" if has_test else "uncovered",
        }

    uncovered_count = sum(1 for f in files_coverage.values() if not f["has_test_file"])
    total = len(files_coverage)

    coverage_report = {
        "files": files_coverage,
        "overall_line_rate": 0.0,  # Phase 4: real data
        "overall_branch_rate": 0.0,
        "build_tool": build_info["build_tool"].value,
        "test_framework": build_info["test_framework"].value,
        "has_coverage_tool": build_info["has_coverage"],
        "coverage_tool": build_info.get("coverage_tool"),
        "coverage_gap": f"{uncovered_count}/{total} changed files have no test file",
        "existing_test_files": list(existing_test_files.values()),
    }

    logger.info(f"Coverage status: {coverage_report['coverage_gap']}")

    return {
        "current_step": "coverage_checker",
        "existing_coverage": coverage_report,
    }


async def _find_existing_tests(
    client, owner: str, repo: str, ref: str,
    changed_files: list[str], build_info: dict,
) -> dict[str, str]:
    """Find existing test files that correspond to changed source files.

    Returns: {source_file_path: test_file_path} for files that have tests.
    """
    test_map = {}

    for source_path in changed_files:
        # Skip non-source files
        if not source_path.endswith((".java", ".py", ".ts", ".kt")):
            continue

        # Generate potential test file paths
        test_paths = _generate_test_paths(source_path)

        for test_path in test_paths:
            try:
                await client.get_file_content(owner, repo, test_path, ref)
                test_map[source_path] = test_path
                logger.info(f"  Found existing test: {test_path}")
                break
            except Exception:
                continue

    return test_map


def _generate_test_paths(source_path: str) -> list[str]:
    """Generate potential test file paths for a given source file."""
    paths = []

    if source_path.endswith(".java"):
        # src/main/java/... → src/test/java/...Test.java
        test_path = source_path.replace("src/main/java/", "src/test/java/")
        base = test_path.removesuffix(".java")
        paths.extend([
            f"{base}Test.java",
            f"{base}Tests.java",
            f"{base}Spec.java",
        ])

    elif source_path.endswith(".py"):
        # my_module.py → test_my_module.py
        from pathlib import Path
        p = Path(source_path)
        paths.extend([
            str(p.parent / f"test_{p.name}"),
            str(Path("tests") / f"test_{p.name}"),
        ])

    return paths


def _empty_coverage() -> dict:
    return {
        "files": {},
        "overall_line_rate": 0.0,
        "overall_branch_rate": 0.0,
        "coverage_gap": "No PR diff available",
    }
