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
        "repo_local_path": "",
        "changed_files": [],
        "generated_tests": [],
        "test_results": [],
        "tests_to_fix": [],
        "messages": [],
        # Mutation testing defaults
        "mutants": [],
        "filtered_mutants": [],
        "mutation_run_results": [],
        "surviving_mutants": [],
        "killing_tests": [],
        "killing_test_results": [],
        "mutation_iteration": 0,
        "mutation_critic_feedback": None,
        "killing_tests_to_fix": [],
        "mutation_score": 0.0,
    }
