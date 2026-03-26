"""Mutation generator node — generates realistic code mutations via LLM."""

import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.engine.prompts.mutation import (
    MUTATION_GENERATOR_SYSTEM_PROMPT,
    build_mutation_prompt,
)
from agent_forge.tools.github.client import GitHubClient

logger = logging.getLogger(__name__)


async def mutation_generator_node(state: AgentState) -> dict:
    """Generate realistic mutations in the PR's changed code.

    Uses a DIFFERENT model (gpt-4o-mini) at higher temperature (0.7) than the
    test generator to prevent AI blind spots — the same model that writes tests
    should not also generate the bugs those tests need to catch.
    """
    settings = get_settings()
    code_analysis = state.get("code_analysis", {}) or {}
    pr_diff = state.get("pr_diff", {}) or {}
    repo = state.get("repo", "")

    logger.info("Generating mutations for changed code")

    # Fetch full source content for changed files
    file_contents: dict[str, str] = {}
    changed_files = state.get("changed_files", [])

    if changed_files and settings.openai_api_key:
        try:
            client = GitHubClient(github_token=settings.github_token)
            head_ref = pr_diff.get("head_ref", "")
            for file_path in changed_files[:5]:  # Cap at 5 files to control cost
                if _is_java_file(file_path):
                    try:
                        content = await client.get_file_content(repo, file_path, ref=head_ref)
                        if content:
                            file_contents[file_path] = content
                    except Exception as e:
                        logger.debug(f"Could not fetch {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Could not fetch file contents: {e}")

    if not settings.openai_api_key:
        logger.warning("No OpenAI API key — using mock mutations")
        return {
            "current_step": "mutation_generator",
            "mutants": _mock_mutants(),
        }

    try:
        mutants = await _generate_mutations(settings, code_analysis, pr_diff, file_contents)
        logger.info(f"Generated {len(mutants)} mutations")
        return {
            "current_step": "mutation_generator",
            "mutants": mutants,
        }
    except Exception as e:
        logger.warning(f"Mutation generation failed ({e}), using mock mutations")
        return {
            "current_step": "mutation_generator",
            "mutants": _mock_mutants(),
        }


async def _generate_mutations(settings, code_analysis, pr_diff, file_contents) -> list[dict]:
    """Use LLM to generate realistic mutations."""
    llm = ChatOpenAI(
        model=settings.mutation_model,
        temperature=settings.mutation_temperature,
        api_key=settings.openai_api_key,
    )

    prompt = build_mutation_prompt(
        code_analysis=code_analysis,
        pr_diff=pr_diff,
        file_contents=file_contents,
    )

    response = await llm.ainvoke([
        SystemMessage(content=MUTATION_GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    mutants = json.loads(content.strip())
    if not isinstance(mutants, list):
        return _mock_mutants()

    # Cap and ensure required fields
    result = []
    for i, m in enumerate(mutants[:settings.max_mutants_per_pr]):
        m.setdefault("mutant_id", f"M{i+1:03d}")
        m.setdefault("line_start", 0)
        m.setdefault("line_end", 0)
        if all(k in m for k in ("mutant_id", "file_path", "original_code", "mutated_code")):
            result.append(m)

    return result if result else _mock_mutants()


def _is_java_file(path: str) -> bool:
    return path.endswith(".java")


def _mock_mutants() -> list[dict]:
    """Fallback mock mutations for offline testing."""
    return [
        {
            "mutant_id": "M001",
            "file_path": "src/main/java/com/demo/agent/common/TransactionMetrics.java",
            "original_code": "successCount.getOrDefault(provider, 0) + 1",
            "mutated_code": "successCount.getOrDefault(provider, 0) - 1",
            "mutation_description": "Wrong operator: decrements success count instead of incrementing",
            "mutation_type": "wrong_operator",
            "line_start": 35,
            "line_end": 35,
        },
        {
            "mutant_id": "M002",
            "file_path": "src/main/java/com/demo/agent/common/TransactionMetrics.java",
            "original_code": "if (total == 0) return 0.0;",
            "mutated_code": "if (total == 0) return 1.0;",
            "mutation_description": "Wrong return value: returns 1.0 (100% success) instead of 0.0 when no transactions",
            "mutation_type": "wrong_return",
            "line_start": 48,
            "line_end": 48,
        },
        {
            "mutant_id": "M003",
            "file_path": "src/main/java/com/demo/agent/common/TransactionMetrics.java",
            "original_code": "totalCount.getOrDefault(provider, 0) + 1",
            "mutated_code": "totalCount.getOrDefault(provider, 0)",
            "mutation_description": "Missing increment: total count never increases, breaking success rate calculation",
            "mutation_type": "wrong_operator",
            "line_start": 34,
            "line_end": 34,
        },
    ]
