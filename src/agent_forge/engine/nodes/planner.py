"""Planner node — validates input and initializes the workflow."""

import logging

from agent_forge.engine.state import AgentState

logger = logging.getLogger(__name__)


async def planner_node(state: AgentState) -> dict:
    """Initialize the workflow: validate inputs, set up working directory."""
    repo = state["repo"]
    pr_number = state["pr_number"]

    logger.info(f"Planning test generation for {repo} PR #{pr_number}")

    return {
        "current_step": "planner",
        "iteration": 0,
        "repo_local_path": "",  # Phase 2: actual clone path
        "changed_files": [],
        "generated_tests": [],
        "test_results": [],
        "tests_to_fix": [],
        "messages": [],
    }
