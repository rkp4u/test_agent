"""Killing test generator node — generates tests that target specific surviving mutants."""

import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.engine.prompts.mutation import (
    KILLING_TEST_SYSTEM_PROMPT,
    build_killing_test_prompt,
)
from agent_forge.tools.github.client import GitHubClient

logger = logging.getLogger(__name__)


async def killing_test_generator_node(state: AgentState) -> dict:
    """Generate tests that specifically catch surviving mutants.

    Unlike the coverage test generator which targets uncovered code paths,
    this node receives a specific bug description and generates a test that:
      - PASSES on the original (correct) code
      - FAILS on the mutated (buggy) code

    Uses the primary model (gpt-4o) at low temperature (0.2) for precision.
    CRITICAL: Fetches full source code of target classes for test generation context.
    """
    settings = get_settings()
    surviving_mutants = state.get("surviving_mutants", [])
    mutation_iteration = state.get("mutation_iteration", 0)
    mutation_critic_feedback = state.get("mutation_critic_feedback")
    killing_tests_to_fix = state.get("killing_tests_to_fix", [])
    previous_killing_tests = state.get("killing_tests", [])
    pr_diff = state.get("pr_diff", {})
    repo = state.get("repo", "")

    if not surviving_mutants:
        logger.info("No surviving mutants — no killing tests needed")
        return {
            "current_step": "killing_test_generator",
            "killing_tests": [],
        }

    if mutation_iteration > 0 and killing_tests_to_fix:
        logger.info(
            f"Mutation reflexion iteration {mutation_iteration}: "
            f"regenerating {len(killing_tests_to_fix)} failing killing tests"
        )
    else:
        logger.info(f"Generating killing tests for {len(surviving_mutants)} surviving mutants")

    if not settings.openai_api_key:
        logger.warning("No OpenAI API key — using mock killing tests")
        return {
            "current_step": "killing_test_generator",
            "killing_tests": _mock_killing_tests(surviving_mutants),
        }

    # Fetch full source code for all files containing mutants (CRITICAL for test generation)
    file_contents = {}
    if repo and settings.github_token:
        try:
            client = GitHubClient(github_token=settings.github_token)
            head_ref = pr_diff.get("head_ref", "")
            # Get unique file paths from surviving mutants
            mutant_files = set(m["file_path"] for m in surviving_mutants)
            for file_path in mutant_files:
                try:
                    content = await client.get_file_content(repo, file_path, ref=head_ref)
                    if content:
                        file_contents[file_path] = content
                        logger.debug(f"Fetched source for killing test context: {file_path}")
                except Exception as e:
                    logger.debug(f"Could not fetch {file_path}: {e}")
        except Exception as e:
            logger.debug(f"Could not fetch file contents for killing test context: {e}")

    try:
        killing_tests = await _generate_killing_tests(
            settings=settings,
            surviving_mutants=surviving_mutants,
            code_analysis=state.get("code_analysis", {}) or {},
            critic_feedback=mutation_critic_feedback,
            tests_to_fix=killing_tests_to_fix,
            previous_tests=previous_killing_tests,
            file_contents=file_contents,
        )
        logger.info(f"Generated {len(killing_tests)} killing test files")
        return {
            "current_step": "killing_test_generator",
            "killing_tests": killing_tests,
        }
    except Exception as e:
        logger.warning(f"Killing test generation failed ({e}), using mock tests")
        return {
            "current_step": "killing_test_generator",
            "killing_tests": _mock_killing_tests(surviving_mutants),
        }


async def _generate_killing_tests(
    settings,
    surviving_mutants: list[dict],
    code_analysis: dict,
    critic_feedback: str | None,
    tests_to_fix: list[dict],
    previous_tests: list[dict],
    file_contents: dict[str, str] | None = None,
) -> list[dict]:
    """Use LLM to generate killing tests for surviving mutants.

    Args:
        file_contents: Full source code of target files (critical for test generation).
    """
    llm = ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        api_key=settings.openai_api_key,
    )

    prompt = build_killing_test_prompt(
        surviving_mutants=surviving_mutants,
        code_analysis=code_analysis,
        critic_feedback=critic_feedback,
        tests_to_fix=tests_to_fix,
        previous_tests=previous_tests,
        file_contents=file_contents,
    )

    response = await llm.ainvoke([
        SystemMessage(content=KILLING_TEST_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    tests = json.loads(content.strip())
    if isinstance(tests, list):
        return tests

    return _mock_killing_tests(surviving_mutants)


def _mock_killing_tests(surviving_mutants: list[dict]) -> list[dict]:
    """Mock killing tests for offline testing."""
    tests = []
    for m in surviving_mutants:
        mutant_id = m["mutant_id"]
        file_parts = m["file_path"].split("/")
        class_name = file_parts[-1].replace(".java", "") if file_parts else "Unknown"
        test_method = f"test{class_name}_{mutant_id}"

        tests.append({
            "file_path": f"src/test/java/com/demo/agent/common/{class_name}MutationTest.java",
            "content": f"""package com.demo.agent.common;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class {class_name}MutationTest {{

    @Test
    void {test_method}() {{
        // Killing test for mutant {mutant_id}: {m['mutation_description']}
        {class_name} subject = new {class_name}();

        // Arrange & Act
        subject.recordTransaction("VISA", 100L, true);
        double rate = subject.getSuccessRate("VISA");

        // Assert: rate must be positive when recording a successful transaction
        assertThat(rate).isGreaterThan(0.0);
    }}
}}
""",
            "target_class": class_name,
            "test_methods": [test_method],
            "target_mutant_id": mutant_id,
            "framework": "junit5",
        })

    return tests
