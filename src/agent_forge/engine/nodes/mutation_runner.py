"""Mutation runner node — runs existing tests against each mutant to find survivors."""

import logging
from pathlib import Path

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.runners.mutation_injector import MutationInjector
from agent_forge.tools.runners.gradle import GradleRunner

logger = logging.getLogger(__name__)


async def mutation_runner_node(state: AgentState) -> dict:
    """Run the existing test suite against each filtered mutant.

    For each mutant:
      1. Inject the mutation (swap original_code → mutated_code in source file)
      2. Run ALL tests (existing + coverage-phase generated tests)
      3. If any test fails → mutant is KILLED
      4. If all tests pass → mutant SURVIVES (needs a killing test)
      5. Restore source file (guaranteed by MutationInjector context manager)
    """
    settings = get_settings()
    filtered_mutants = state.get("filtered_mutants", [])
    repo_local_path = state.get("repo_local_path", "")

    if not filtered_mutants:
        logger.info("No filtered mutants to run")
        return {
            "current_step": "mutation_runner",
            "mutation_run_results": [],
            "surviving_mutants": [],
        }

    if not repo_local_path:
        logger.warning("No local repo path — using mock mutation run results")
        return _mock_results(filtered_mutants)

    repo_path = Path(repo_local_path)
    if not (repo_path / "gradlew").exists():
        logger.warning(f"No gradlew at {repo_path} — using mock mutation run results")
        return _mock_results(filtered_mutants)

    injector = MutationInjector(repo_path)
    runner = GradleRunner(repo_path)
    results = []
    surviving_mutants = []

    try:
        for mutant in filtered_mutants:
            mutant_id = mutant["mutant_id"]
            logger.info(f"Testing mutant {mutant_id}: {mutant['mutation_description']}")

            run_result = await _run_single_mutant(injector, runner, mutant, settings)
            results.append(run_result)

            if run_result.get("build_failed"):
                logger.info(f"  ↳ BUILD FAILED: {mutant_id} — mutant doesn't compile (skipped)")
            elif run_result.get("killed"):
                logger.info(f"  ↳ KILLED by: {run_result.get('killing_test', 'existing tests')}")
            else:
                surviving_mutants.append(mutant)
                logger.info(f"  ↳ SURVIVED: {mutant_id} — no existing test catches this bug")

    finally:
        injector.restore_all()

    killed = sum(1 for r in results if r.get("killed"))
    survived = len(surviving_mutants)
    build_failed = sum(1 for r in results if r.get("build_failed"))
    logger.info(
        f"Mutation run complete: {killed} killed, {survived} survived, {build_failed} build failures"
    )

    return {
        "current_step": "mutation_runner",
        "mutation_run_results": results,
        "surviving_mutants": surviving_mutants,
    }


async def _run_single_mutant(injector: MutationInjector, runner: GradleRunner, mutant: dict, settings) -> dict:
    """Inject a single mutant, run tests, restore, return result dict."""
    mutant_id = mutant["mutant_id"]

    with injector.inject_mutant(mutant) as injected:
        if not injected:
            return {
                "mutant_id": mutant_id,
                "killed": False,
                "survived": False,
                "build_failed": True,
                "killing_test": None,
            }

        try:
            result = await runner.run_tests(timeout=settings.test_timeout_seconds)

            # If compilation failed, treat as build failure
            if hasattr(result, "compilation_errors") and result.compilation_errors:
                return {
                    "mutant_id": mutant_id,
                    "killed": False,
                    "survived": False,
                    "build_failed": True,
                    "killing_test": None,
                }

            test_results = result.test_results if hasattr(result, "test_results") else []
            failed_tests = [t for t in test_results if not t.get("passed")]

            if failed_tests:
                return {
                    "mutant_id": mutant_id,
                    "killed": True,
                    "survived": False,
                    "build_failed": False,
                    "killing_test": failed_tests[0].get("test_name"),
                }
            else:
                return {
                    "mutant_id": mutant_id,
                    "killed": False,
                    "survived": True,
                    "build_failed": False,
                    "killing_test": None,
                }

        except Exception as e:
            logger.warning(f"Test run error for mutant {mutant_id}: {e}")
            return {
                "mutant_id": mutant_id,
                "killed": False,
                "survived": True,
                "build_failed": False,
                "killing_test": None,
            }


def _mock_results(mutants: list[dict]) -> dict:
    """Mock results for offline testing — all mutants survive."""
    results = []
    surviving = []
    for m in mutants:
        results.append({
            "mutant_id": m["mutant_id"],
            "killed": False,
            "survived": True,
            "build_failed": False,
            "killing_test": None,
        })
        surviving.append(m)

    logger.info(f"Mock: {len(surviving)} mutants survive (no real test run)")
    return {
        "current_step": "mutation_runner",
        "mutation_run_results": results,
        "surviving_mutants": surviving,
    }
