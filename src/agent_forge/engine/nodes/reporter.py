"""Reporter node — generates the final structured report."""

import logging
from datetime import datetime, timezone

from agent_forge.engine.state import AgentState

logger = logging.getLogger(__name__)


async def reporter_node(state: AgentState) -> dict:
    """Generate the final test generation report."""
    pr_diff = state.get("pr_diff", {})
    existing_coverage = state.get("existing_coverage", {})
    new_coverage = state.get("new_coverage", {})
    generated_tests = state.get("generated_tests", [])
    test_results = state.get("test_results", [])
    iteration = state.get("iteration", 1)

    passed = sum(1 for t in test_results if t.get("passed", False))
    failed = sum(1 for t in test_results if not t.get("passed", False))

    coverage_before = existing_coverage.get("overall_line_rate", 0.0)
    coverage_after = new_coverage.get("overall_line_rate", 0.0) if new_coverage else 0.0

    # Build per-file coverage comparison
    coverage_comparisons = []
    if new_coverage and existing_coverage:
        for file_path, new_cov in new_coverage.get("files", {}).items():
            old_cov = existing_coverage.get("files", {}).get(file_path, {})
            coverage_comparisons.append({
                "file_path": file_path,
                "before_line_rate": old_cov.get("line_rate", 0.0),
                "after_line_rate": new_cov.get("line_rate", 0.0),
            })

    total_test_methods = sum(len(t.get("test_methods", [])) for t in generated_tests)

    report = {
        "repo": state["repo"],
        "pr_number": state["pr_number"],
        "pr_title": pr_diff.get("title", "Unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_analyzed": state.get("changed_files", []),
        "methods_found": len(state.get("untested_targets", [])),
        "uncovered_methods": len(state.get("untested_targets", [])),
        "tests_generated": total_test_methods,
        "test_files_created": [t.get("file_path", "") for t in generated_tests],
        "tests_passed": passed,
        "tests_failed": failed,
        "test_results": test_results,
        "iterations_used": iteration,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "coverage_comparisons": coverage_comparisons,
        "tool_calls": 5,  # planner + diff + analyze + coverage + generate + run
        "suggestions": _generate_suggestions(test_results, coverage_after),
    }

    logger.info(
        f"Report generated: {passed} passed, {failed} failed, "
        f"coverage {coverage_before:.0%} → {coverage_after:.0%}"
    )

    return {
        "current_step": "reporter",
        "report": report,
    }


def _generate_suggestions(test_results: list[dict], coverage_after: float) -> list[str]:
    """Generate actionable suggestions based on results."""
    suggestions = []

    failed = [t for t in test_results if not t.get("passed", False)]
    if failed:
        suggestions.append(
            f"{len(failed)} tests still failing after reflexion — manual review recommended"
        )

    if coverage_after < 0.8:
        suggestions.append(
            "Coverage below 80% — consider adding integration tests for remaining paths"
        )

    if any("backoff" in t.get("test_name", "").lower() for t in test_results):
        suggestions.append(
            "Backoff timing test may need adjustment for CI environments with variable speed"
        )

    return suggestions
