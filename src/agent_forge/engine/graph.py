"""LangGraph graph definition — Plan-and-Execute with Reflexion + Mutation Testing."""

import logging

from langgraph.graph import StateGraph, START, END

from agent_forge.engine.state import AgentState
from agent_forge.engine.nodes import (
    planner_node,
    diff_fetcher_node,
    code_analyzer_node,
    coverage_checker_node,
    test_generator_node,
    test_runner_node,
    critic_node,
    reporter_node,
    mutation_generator_node,
    equivalence_detector_node,
    mutation_runner_node,
    killing_test_generator_node,
    killing_test_runner_node,
    mutation_critic_node,
)

logger = logging.getLogger(__name__)

MAX_REFLEXION_ITERATIONS = 3
MAX_MUTATION_REFLEXION_ITERATIONS = 2


def should_retry(state: AgentState) -> str:
    """Conditional edge: decide whether to retry test generation or proceed.

    In coverage mode → done goes to reporter.
    In mutation mode → done goes to mutation_generator (start mutation pipeline).
    Returns 'retry', 'mutation', or 'done'.
    """
    iteration = state.get("iteration", 0)
    tests_to_fix = state.get("tests_to_fix", [])

    if iteration >= MAX_REFLEXION_ITERATIONS:
        logger.info(f"Max reflexion iterations ({MAX_REFLEXION_ITERATIONS}) reached")
        return _after_coverage(state)

    if tests_to_fix and len(tests_to_fix) > 0:
        logger.info(f"Retrying: {len(tests_to_fix)} tests to fix (iteration {iteration})")
        return "retry"

    logger.info("Coverage phase complete — proceeding")
    return _after_coverage(state)


def _after_coverage(state: AgentState) -> str:
    """After coverage phase completes, route based on mode."""
    mode = state.get("mode", "coverage")
    if mode == "mutation":
        return "mutation"
    return "done"


def should_retry_mutation(state: AgentState) -> str:
    """Conditional edge for mutation reflexion loop.

    Returns 'retry' if killing tests failed and we haven't exceeded max iterations.
    Returns 'done' otherwise.
    """
    mutation_iteration = state.get("mutation_iteration", 0)
    killing_tests_to_fix = state.get("killing_tests_to_fix", [])

    if mutation_iteration >= MAX_MUTATION_REFLEXION_ITERATIONS:
        logger.info(f"Max mutation reflexion iterations ({MAX_MUTATION_REFLEXION_ITERATIONS}) reached")
        return "done"

    if killing_tests_to_fix and len(killing_tests_to_fix) > 0:
        logger.info(
            f"Mutation reflexion: {len(killing_tests_to_fix)} killing tests to fix "
            f"(iteration {mutation_iteration})"
        )
        return "retry"

    logger.info("All killing tests accepted — proceeding to report")
    return "done"


def build_graph() -> StateGraph:
    """Build the agent workflow graph.

    Architecture: Plan-and-Execute with Reflexion + optional Mutation Pipeline.

    Coverage mode flow (default):
        START → planner → diff_fetcher → code_analyzer → coverage_checker
              → test_generator → test_runner → critic
              → critic (done) → reporter → END
              → critic (retry) → test_generator  [max 3 iterations]

    Mutation mode flow (--mode mutation):
        ... same coverage phase ...
        → critic (done/mutation) → mutation_generator → equivalence_detector
        → mutation_runner → killing_test_generator → killing_test_runner
        → mutation_critic (done) → reporter → END
        → mutation_critic (retry) → killing_test_generator  [max 2 iterations]
    """
    graph = StateGraph(AgentState)

    # --- Coverage phase nodes (unchanged) ---
    graph.add_node("planner", planner_node)
    graph.add_node("diff_fetcher", diff_fetcher_node)
    graph.add_node("code_analyzer", code_analyzer_node)
    graph.add_node("coverage_checker", coverage_checker_node)
    graph.add_node("test_generator", test_generator_node)
    graph.add_node("test_runner", test_runner_node)
    graph.add_node("critic", critic_node)
    graph.add_node("reporter", reporter_node)

    # --- Mutation phase nodes ---
    graph.add_node("mutation_generator", mutation_generator_node)
    graph.add_node("equivalence_detector", equivalence_detector_node)
    graph.add_node("mutation_runner", mutation_runner_node)
    graph.add_node("killing_test_generator", killing_test_generator_node)
    graph.add_node("killing_test_runner", killing_test_runner_node)
    graph.add_node("mutation_critic", mutation_critic_node)

    # --- Coverage phase edges (unchanged) ---
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "diff_fetcher")
    graph.add_edge("diff_fetcher", "code_analyzer")
    graph.add_edge("code_analyzer", "coverage_checker")
    graph.add_edge("coverage_checker", "test_generator")
    graph.add_edge("test_generator", "test_runner")
    graph.add_edge("test_runner", "critic")

    # Conditional after critic: retry | done (coverage mode) | mutation (mutation mode)
    graph.add_conditional_edges(
        "critic",
        should_retry,
        {
            "retry": "test_generator",
            "done": "reporter",
            "mutation": "mutation_generator",
        },
    )

    # --- Mutation phase edges ---
    graph.add_edge("mutation_generator", "equivalence_detector")
    graph.add_edge("equivalence_detector", "mutation_runner")
    graph.add_edge("mutation_runner", "killing_test_generator")
    graph.add_edge("killing_test_generator", "killing_test_runner")
    graph.add_edge("killing_test_runner", "mutation_critic")

    # Conditional after mutation_critic: retry killing tests | done → reporter
    graph.add_conditional_edges(
        "mutation_critic",
        should_retry_mutation,
        {
            "retry": "killing_test_generator",
            "done": "reporter",
        },
    )

    # Final
    graph.add_edge("reporter", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    graph = build_graph()
    return graph.compile()
