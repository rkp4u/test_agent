"""Equivalence detector node — filters out semantically equivalent mutations."""

import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.engine.prompts.mutation import (
    EQUIVALENCE_JUDGE_SYSTEM_PROMPT,
    build_equivalence_prompt,
)

logger = logging.getLogger(__name__)


async def equivalence_detector_node(state: AgentState) -> dict:
    """Filter equivalent mutants using LLM-as-judge.

    An equivalent mutant produces identical behavior to the original — no test
    can distinguish it. Filtering these out avoids wasting build cycles.

    Uses gpt-4o-mini at temperature 0.0 (deterministic, cheap classification).
    Expect ~0.79 precision per Meta ACH paper — residual false positives are
    caught by the 3-stage filter in killing_test_runner.
    """
    settings = get_settings()
    mutants = state.get("mutants", [])

    if not mutants:
        logger.info("No mutants to filter")
        return {"current_step": "equivalence_detector", "filtered_mutants": []}

    logger.info(f"Filtering {len(mutants)} mutants for equivalence")

    if not settings.openai_api_key:
        logger.warning("No OpenAI API key — keeping all mutants (no equivalence filtering)")
        return {
            "current_step": "equivalence_detector",
            "filtered_mutants": mutants,
        }

    try:
        filtered = await _filter_equivalent(settings, mutants)
        removed = len(mutants) - len(filtered)
        logger.info(f"Equivalence filtering: kept {len(filtered)}, removed {removed} equivalent mutants")
        return {
            "current_step": "equivalence_detector",
            "filtered_mutants": filtered,
        }
    except Exception as e:
        logger.warning(f"Equivalence detection failed ({e}), keeping all mutants")
        return {
            "current_step": "equivalence_detector",
            "filtered_mutants": mutants,
        }


async def _filter_equivalent(settings, mutants: list[dict]) -> list[dict]:
    """Use LLM to classify each mutant as equivalent or non-equivalent."""
    llm = ChatOpenAI(
        model=settings.equivalence_model,
        temperature=settings.equivalence_temperature,
        api_key=settings.openai_api_key,
    )

    # Process in batches of 10 to stay within context limits
    all_verdicts: dict[str, str] = {}
    batch_size = 10

    for i in range(0, len(mutants), batch_size):
        batch = mutants[i:i + batch_size]
        prompt = build_equivalence_prompt(batch)

        response = await llm.ainvoke([
            SystemMessage(content=EQUIVALENCE_JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        verdicts = json.loads(content.strip())
        if isinstance(verdicts, list):
            for v in verdicts:
                mutant_id = v.get("mutant_id", "")
                verdict = v.get("verdict", "non_equivalent")
                all_verdicts[mutant_id] = verdict

    # Keep only non-equivalent mutants
    filtered = []
    for m in mutants:
        verdict = all_verdicts.get(m["mutant_id"], "non_equivalent")
        if verdict != "equivalent":
            filtered.append(m)
        else:
            logger.debug(f"Filtered equivalent mutant: {m['mutant_id']} — {m['mutation_description']}")

    return filtered
