"""Critic node — evaluates test results and decides whether to retry."""

import logging

from agent_forge.engine.state import AgentState

logger = logging.getLogger(__name__)


async def critic_node(state: AgentState) -> dict:
    """Analyze test results. Identify failures and provide feedback for regeneration.

    The critic examines each failed test and classifies the failure:
    - compilation: missing imports, wrong types, private field access, syntax errors
    - runtime: NPE, ClassNotFoundException, missing mocks
    - assertion: wrong expected values, incorrect assumptions
    - infrastructure: build tool issues, timeout, env problems

    Returns tests_to_fix list and increments iteration counter.
    """
    test_results = state.get("test_results", [])
    iteration = state.get("iteration", 0)

    failed_tests = [t for t in test_results if not t.get("passed", False) and not t.get("skipped", False)]
    passed_tests = [t for t in test_results if t.get("passed", False)]

    logger.info(
        f"Critic evaluation: {len(passed_tests)} passed, {len(failed_tests)} failed "
        f"(iteration {iteration + 1})"
    )

    if not failed_tests:
        logger.info("All tests passed — no reflexion needed")
        return {
            "current_step": "critic",
            "iteration": iteration + 1,
            "tests_to_fix": [],
            "critic_feedback": None,
        }

    # Classify failures and build detailed feedback
    tests_to_fix = []
    feedback_parts = []

    for test in failed_tests:
        test_name = test.get("test_name", "unknown")
        error = test.get("error_message", "No error message available")
        failure_type = _classify_failure(error)

        tests_to_fix.append({
            "test_name": test_name,
            "error_message": error,
            "failure_type": failure_type,
        })

        feedback_parts.append(f"- [{failure_type.upper()}] {test_name}: {error}")

    # Build actionable feedback
    failure_types = set(t["failure_type"] for t in tests_to_fix)
    advice = []

    if "compilation" in failure_types:
        advice.append(
            "COMPILATION ERRORS DETECTED. Common fixes:\n"
            "  - Do NOT access private fields directly (e.g., obj.privateField). "
            "Use public getters/methods instead.\n"
            "  - Ensure all imports are present.\n"
            "  - Check method signatures match the actual class."
        )

    if "assertion" in failure_types:
        advice.append(
            "ASSERTION FAILURES. The test logic may be wrong:\n"
            "  - Double-check expected values against the actual code behavior.\n"
            "  - Review boundary conditions."
        )

    if "runtime" in failure_types:
        advice.append(
            "RUNTIME ERRORS. Likely missing setup:\n"
            "  - Ensure all mocks are properly initialized.\n"
            "  - Check for NullPointerExceptions — a dependency may not be mocked."
        )

    critic_feedback = (
        f"Iteration {iteration + 1}: {len(failed_tests)} tests failed out of "
        f"{len(passed_tests) + len(failed_tests)} total.\n\n"
        f"FAILURES:\n" + "\n".join(feedback_parts) + "\n\n"
        f"FIX INSTRUCTIONS:\n" + "\n".join(advice) + "\n\n"
        f"Regenerate ONLY the failing tests with these fixes applied. "
        f"Keep all passing tests exactly as they are."
    )

    logger.info(f"Critic feedback: {len(tests_to_fix)} tests to fix ({', '.join(failure_types)})")

    return {
        "current_step": "critic",
        "iteration": iteration + 1,
        "tests_to_fix": tests_to_fix,
        "critic_feedback": critic_feedback,
    }


def _classify_failure(error_message: str) -> str:
    """Classify a test failure by its error message."""
    error_lower = error_message.lower() if error_message else ""

    # Compilation errors
    compilation_patterns = [
        "has private access",
        "cannot find symbol",
        "incompatible types",
        "cannot be applied to",
        "does not exist",
        "is not abstract and does not override",
        "unreported exception",
        "error:",
        "cannot resolve",
    ]
    if any(p in error_lower for p in compilation_patterns):
        return "compilation"

    # Runtime errors
    runtime_patterns = [
        "nullpointerexception",
        "classnotfoundexception",
        "nosuchmethoderror",
        "illegalargumentexception",
        "classcastexception",
        "stackoverflowerror",
    ]
    if any(p in error_lower for p in runtime_patterns):
        return "runtime"

    # Assertion errors
    assertion_patterns = [
        "expected",
        "assertionerror",
        "comparison failure",
        "not equal",
        "but was",
    ]
    if any(p in error_lower for p in assertion_patterns):
        return "assertion"

    return "unknown"
