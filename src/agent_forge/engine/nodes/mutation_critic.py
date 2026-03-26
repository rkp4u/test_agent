"""Mutation critic node — evaluates killing test results and provides reflexion feedback."""

import logging

from agent_forge.engine.state import AgentState

logger = logging.getLogger(__name__)

# Maps stage failure → human-readable advice for the killing test generator
_STAGE_ADVICE = {
    "compilation": (
        "The test failed to compile. Common causes:\n"
        "  • Accessing private fields or methods (use public API only)\n"
        "  • Missing imports (include all necessary import statements)\n"
        "  • Wrong class/method names (check the source code carefully)\n"
        "  • Incorrect package declaration (must match source package)\n"
        "Fix: ensure the test compiles cleanly against the original code."
    ),
    "passes_original": (
        "The test FAILS on the original (correct) code — this means the test itself is wrong.\n"
        "The assertion must be TRUE for the correct behavior and FALSE for the buggy behavior.\n"
        "Fix: reverse your assertion logic, or re-read the original code to understand the correct output."
    ),
    "fails_mutant": (
        "The test PASSES on the mutated (buggy) code — it does not detect the specific bug.\n"
        "The test needs a tighter assertion that distinguishes the original from the mutated behavior.\n"
        "Fix: assert the exact value or behavior that the mutation changes."
    ),
}


def _classify_failure(result: dict) -> str:
    """Classify why a killing test failed the 3-stage filter."""
    if not result.get("builds"):
        return "compilation"
    if not result.get("passes_original"):
        return "passes_original"
    if not result.get("fails_mutant"):
        return "fails_mutant"
    return "unknown"


async def mutation_critic_node(state: AgentState) -> dict:
    """Evaluate 3-stage filter results and prepare reflexion feedback.

    Identifies killing tests that failed any stage, classifies the failure type,
    and produces structured feedback for the killing_test_generator on retry.

    Pure rule-based — no LLM needed. The 3-stage filter already provides
    all the information needed for targeted feedback.
    """
    killing_test_results = state.get("killing_test_results", [])
    mutation_iteration = state.get("mutation_iteration", 0)
    surviving_mutants = state.get("surviving_mutants", [])

    mutation_iteration += 1

    failing = [r for r in killing_test_results if not r.get("accepted")]
    passing = [r for r in killing_test_results if r.get("accepted")]

    logger.info(
        f"Mutation critic (iteration {mutation_iteration}): "
        f"{len(passing)} accepted, {len(failing)} need fixing"
    )

    if not failing:
        logger.info("All killing tests accepted — mutation testing complete")
        # Compute mutation score
        total_non_equiv = len(state.get("filtered_mutants", []))
        killed_by_existing = sum(
            1 for r in state.get("mutation_run_results", []) if r.get("killed")
        )
        killed_by_new = len(passing)
        total_killed = killed_by_existing + killed_by_new
        score = (total_killed / total_non_equiv) if total_non_equiv > 0 else 0.0

        return {
            "current_step": "mutation_critic",
            "mutation_iteration": mutation_iteration,
            "killing_tests_to_fix": [],
            "mutation_critic_feedback": None,
            "mutation_score": round(score, 3),
        }

    # Classify each failing test
    to_fix = []
    feedback_parts = []

    for result in failing:
        failure_type = _classify_failure(result)
        advice = _STAGE_ADVICE.get(failure_type, "Unknown failure — review test logic.")

        to_fix.append({
            "test_name": result["test_name"],
            "mutant_id": result["mutant_id"],
            "failure_type": failure_type,
            "error_message": result.get("error_message", ""),
            "stage_advice": advice,
        })

        mutant = next(
            (m for m in surviving_mutants if m["mutant_id"] == result["mutant_id"]),
            {}
        )
        feedback_parts.append(
            f"• {result['test_name']} (targeting {result['mutant_id']}):\n"
            f"  Failure: {failure_type}\n"
            f"  Error: {result.get('error_message', 'n/a')}\n"
            f"  Mutation: {mutant.get('mutation_description', 'n/a')}\n"
            f"  Fix: {advice}\n"
        )

    feedback = (
        f"# Mutation Reflexion Feedback (iteration {mutation_iteration})\n\n"
        f"{len(failing)} killing test(s) failed the 3-stage filter:\n\n"
        + "\n".join(feedback_parts)
    )

    return {
        "current_step": "mutation_critic",
        "mutation_iteration": mutation_iteration,
        "killing_tests_to_fix": to_fix,
        "mutation_critic_feedback": feedback,
        "mutation_score": 0.0,  # Will be set properly when all pass
    }
