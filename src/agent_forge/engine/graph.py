"""LangGraph graph definition — Plan-and-Execute with Reflexion."""

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
)

logger = logging.getLogger(__name__)

MAX_REFLEXION_ITERATIONS = 3


def should_retry(state: AgentState) -> str:
    """Conditional edge: decide whether to retry test generation or finalize report.

    Returns 'retry' if there are failing tests and we haven't exceeded max iterations.
    Returns 'done' otherwise.
    """
    iteration = state.get("iteration", 0)
    tests_to_fix = state.get("tests_to_fix", [])

    if iteration >= MAX_REFLEXION_ITERATIONS:
        logger.info(f"Max reflexion iterations ({MAX_REFLEXION_ITERATIONS}) reached — finalizing")
        return "done"

    if tests_to_fix and len(tests_to_fix) > 0:
        logger.info(f"Retrying: {len(tests_to_fix)} tests to fix (iteration {iteration})")
        return "retry"

    logger.info("All tests passed — proceeding to report")
    return "done"


def build_graph() -> StateGraph:
    """Build the agent workflow graph.

    Architecture: Plan-and-Execute with Reflexion loop.

    Flow:
        START → planner → diff_fetcher → code_analyzer → test_generator
                                       → coverage_checker ↗
        test_generator → test_runner → critic
        critic → (retry) → test_generator  [reflexion loop, max 3]
        critic → (done) → reporter → END
    """
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("planner", planner_node)
    graph.add_node("diff_fetcher", diff_fetcher_node)
    graph.add_node("code_analyzer", code_analyzer_node)
    graph.add_node("coverage_checker", coverage_checker_node)
    graph.add_node("test_generator", test_generator_node)
    graph.add_node("test_runner", test_runner_node)
    graph.add_node("critic", critic_node)
    graph.add_node("reporter", reporter_node)

    # Linear flow: START → planner → diff_fetcher
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "diff_fetcher")

    # Sequential: diff_fetcher → code_analyzer → coverage_checker → test_generator
    # Note: These could run in parallel with annotated state reducers (Phase 3 optimization)
    graph.add_edge("diff_fetcher", "code_analyzer")
    graph.add_edge("code_analyzer", "coverage_checker")
    graph.add_edge("coverage_checker", "test_generator")

    # Sequential: test_generator → test_runner → critic
    graph.add_edge("test_generator", "test_runner")
    graph.add_edge("test_runner", "critic")

    # Conditional: critic decides retry or done
    graph.add_conditional_edges(
        "critic",
        should_retry,
        {
            "retry": "test_generator",
            "done": "reporter",
        },
    )

    # Final: reporter → END
    graph.add_edge("reporter", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    graph = build_graph()
    return graph.compile()
