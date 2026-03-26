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

    # Mutation testing data
    mode = state.get("mode", "coverage")
    mutation_report = None
    if mode == "mutation":
        mutation_run_results = state.get("mutation_run_results", [])
        killing_test_results = state.get("killing_test_results", [])
        filtered_mutants = state.get("filtered_mutants", [])
        all_mutants = state.get("mutants", [])
        killed_by_existing = sum(1 for r in mutation_run_results if r.get("killed"))
        killed_by_new = sum(1 for r in killing_test_results if r.get("accepted"))
        survived = sum(1 for r in mutation_run_results if r.get("survived"))
        build_failed = sum(1 for r in mutation_run_results if r.get("build_failed"))
        total_non_equiv = len(filtered_mutants)
        total_killed = killed_by_existing + killed_by_new
        mutation_score = state.get("mutation_score", 0.0)
        if mutation_score == 0.0 and total_non_equiv > 0:
            mutation_score = round(total_killed / total_non_equiv, 3)

        mutation_report = {
            "total_mutants_generated": len(all_mutants),
            "equivalent_filtered": len(all_mutants) - total_non_equiv,
            "mutants_tested": total_non_equiv,
            "killed_by_existing": killed_by_existing,
            "killed_by_new": killed_by_new,
            "survived": survived - killed_by_new,  # Subtract those caught by killing tests
            "build_failed": build_failed,
            "mutation_score": mutation_score,
            "surviving_mutant_details": [
                m for m in state.get("surviving_mutants", [])
                if m["mutant_id"] not in {r["mutant_id"] for r in killing_test_results if r.get("accepted")}
            ],
        }

    report = {
        "repo": state["repo"],
        "pr_number": state["pr_number"],
        "pr_title": pr_diff.get("title", "Unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
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
        "tool_calls": 5,
        "mutation": mutation_report,
        "suggestions": _generate_suggestions(test_results, coverage_after, mutation_report),
    }

    if mode == "mutation" and mutation_report:
        logger.info(
            f"Report generated: {passed} passed, {failed} failed, "
            f"mutation score {mutation_report['mutation_score']:.0%} "
            f"({mutation_report['killed_by_existing']} killed by existing + "
            f"{mutation_report['killed_by_new']} by new tests)"
        )
    else:
        logger.info(
            f"Report generated: {passed} passed, {failed} failed, "
            f"coverage {coverage_before:.0%} → {coverage_after:.0%}"
        )

    return {
        "current_step": "reporter",
        "report": report,
    }


def _generate_suggestions(
    test_results: list[dict], coverage_after: float, mutation_report: dict | None = None
) -> list[str]:
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

    if mutation_report:
        survived = mutation_report.get("survived", 0)
        score = mutation_report.get("mutation_score", 0.0)
        if survived > 0:
            suggestions.append(
                f"{survived} mutant(s) still surviving — consider manual review of surviving cases"
            )
        if score < 0.8:
            suggestions.append(
                "Mutation score below 80% — consider adding more targeted tests for edge cases"
            )
        if mutation_report.get("killed_by_new", 0) > 0:
            suggestions.append(
                f"{mutation_report['killed_by_new']} new killing test(s) added — "
                "commit these to prevent future regression"
            )

    return suggestions
