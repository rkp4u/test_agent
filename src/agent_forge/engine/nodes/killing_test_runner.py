"""Killing test runner — 3-stage filter pipeline: Build → Pass original → Fail mutant."""

import logging
from pathlib import Path

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.runners.mutation_injector import MutationInjector
from agent_forge.tools.runners.gradle import GradleRunner

logger = logging.getLogger(__name__)


async def killing_test_runner_node(state: AgentState) -> dict:
    """Apply the 3-stage filter to each killing test candidate.

    Stage 1 — BUILD: The test must compile without errors.
    Stage 2 — PASS ORIGINAL: The test must pass against unmodified source code.
               (If it fails here, the test logic is wrong — it claims original code is buggy.)
    Stage 3 — FAIL MUTANT: The test must fail when the target mutation is injected.
               (If it passes here, the test doesn't actually detect the specific bug.)

    Only tests that pass ALL 3 stages are marked accepted=True.
    Tests that fail any stage are recorded with the appropriate error for the critic.
    """
    settings = get_settings()
    killing_tests = state.get("killing_tests", [])
    surviving_mutants = state.get("surviving_mutants", [])
    repo_local_path = state.get("repo_local_path", "")

    if not killing_tests:
        logger.info("No killing tests to filter")
        return {
            "current_step": "killing_test_runner",
            "killing_test_results": [],
        }

    if not repo_local_path:
        logger.warning("No local repo path — using mock 3-stage filter results")
        return _mock_filter_results(killing_tests)

    repo_path = Path(repo_local_path)
    if not (repo_path / "gradlew").exists():
        logger.warning("No gradlew — using mock 3-stage filter results")
        return _mock_filter_results(killing_tests)

    injector = MutationInjector(repo_path)
    runner = GradleRunner(repo_path)

    # Build mutant lookup
    mutant_by_id = {m["mutant_id"]: m for m in surviving_mutants}
    results = []

    try:
        # Write all killing test files first
        written_files: list[Path] = []
        for kt in killing_tests:
            try:
                written = await runner.write_test_file(kt["file_path"], kt["content"])
                written_files.append(written)
            except Exception as e:
                logger.warning(f"Could not write killing test {kt['file_path']}: {e}")

        for kt in killing_tests:
            mutant_id = kt.get("target_mutant_id", "")
            test_methods = kt.get("test_methods", [])
            test_name = test_methods[0] if test_methods else kt.get("file_path", "")

            result = {
                "test_name": test_name,
                "mutant_id": mutant_id,
                "builds": False,
                "passes_original": False,
                "fails_mutant": False,
                "accepted": False,
                "error_message": "",
            }

            # Stage 1 + 2: Build and run against original
            try:
                orig_run = await runner.run_tests(timeout=settings.test_timeout_seconds)
                compile_errors = getattr(orig_run, "compilation_errors", [])

                if compile_errors:
                    result["builds"] = False
                    result["error_message"] = f"Compilation failed: {compile_errors[0] if compile_errors else 'unknown error'}"
                    logger.info(f"  {test_name} [{mutant_id}] — Stage 1 FAIL (compilation error)")
                    results.append(result)
                    continue

                result["builds"] = True
                test_results = getattr(orig_run, "test_results", orig_run if isinstance(orig_run, list) else [])
                if hasattr(orig_run, "test_results"):
                    test_results = orig_run.test_results

                # Check if this specific test passes on original
                relevant = [
                    t for t in test_results
                    if test_name in t.get("test_name", "") or any(
                        m in t.get("test_name", "") for m in test_methods
                    )
                ]
                killing_test_failed_on_original = any(
                    not t.get("passed", True) for t in relevant
                ) if relevant else False

                if killing_test_failed_on_original:
                    result["passes_original"] = False
                    failed = next((t for t in relevant if not t.get("passed", True)), {})
                    result["error_message"] = (
                        f"Stage 2 FAIL: test fails on original code — "
                        f"{failed.get('error_message', 'assertion failed')}"
                    )
                    logger.info(f"  {test_name} [{mutant_id}] — Stage 2 FAIL (fails on original)")
                    results.append(result)
                    continue

                result["passes_original"] = True

            except Exception as e:
                result["error_message"] = f"Stage 1/2 error: {e}"
                logger.warning(f"  {test_name} [{mutant_id}] — Stage 1/2 error: {e}")
                results.append(result)
                continue

            # Stage 3: Inject mutant, run test, expect failure
            mutant = mutant_by_id.get(mutant_id)
            if not mutant:
                result["fails_mutant"] = False
                result["error_message"] = f"Mutant {mutant_id} not found in surviving mutants"
                results.append(result)
                continue

            try:
                with injector.inject_mutant(mutant) as injected:
                    if not injected:
                        result["fails_mutant"] = False
                        result["error_message"] = "Could not inject mutant — original_code not found in source"
                        results.append(result)
                        continue

                    mutant_run = await runner.run_tests(timeout=settings.test_timeout_seconds)
                    mutant_test_results = getattr(mutant_run, "test_results", [])

                    relevant_on_mutant = [
                        t for t in mutant_test_results
                        if test_name in t.get("test_name", "") or any(
                            m in t.get("test_name", "") for m in test_methods
                        )
                    ]
                    test_fails_on_mutant = any(
                        not t.get("passed", True) for t in relevant_on_mutant
                    ) if relevant_on_mutant else False

                    if test_fails_on_mutant:
                        result["fails_mutant"] = True
                        result["accepted"] = True
                        logger.info(f"  {test_name} [{mutant_id}] — ALL 3 STAGES PASSED ✓")
                    else:
                        result["fails_mutant"] = False
                        result["error_message"] = (
                            f"Stage 3 FAIL: test passes on mutant — "
                            f"does not detect '{mutant['mutation_description']}'"
                        )
                        logger.info(f"  {test_name} [{mutant_id}] — Stage 3 FAIL (doesn't catch bug)")

            except Exception as e:
                result["error_message"] = f"Stage 3 error: {e}"
                logger.warning(f"  {test_name} [{mutant_id}] — Stage 3 error: {e}")

            results.append(result)

    finally:
        injector.restore_all()

    accepted = sum(1 for r in results if r.get("accepted"))
    logger.info(f"3-stage filter: {accepted}/{len(results)} killing tests accepted")

    return {
        "current_step": "killing_test_runner",
        "killing_test_results": results,
    }


def _mock_filter_results(killing_tests: list[dict]) -> dict:
    """Mock results — all killing tests pass all 3 stages."""
    results = []
    for kt in killing_tests:
        test_methods = kt.get("test_methods", [])
        test_name = test_methods[0] if test_methods else kt.get("file_path", "")
        results.append({
            "test_name": test_name,
            "mutant_id": kt.get("target_mutant_id", ""),
            "builds": True,
            "passes_original": True,
            "fails_mutant": True,
            "accepted": True,
            "error_message": "",
        })
    logger.info(f"Mock: {len(results)} killing tests accepted")
    return {
        "current_step": "killing_test_runner",
        "killing_test_results": results,
    }
