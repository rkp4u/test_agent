"""Agent state definition for the LangGraph workflow."""

from typing import Annotated, TypedDict

from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Central state flowing through the LangGraph workflow.

    Each node reads from and writes to this state. LangGraph handles
    merging partial updates from each node.
    """

    # --- Input ---
    repo: str  # owner/repo format
    pr_number: int
    repo_local_path: str  # Local clone path

    # --- PR Data ---
    pr_diff: dict | None  # Serialized PRDiff
    changed_files: list[str]

    # --- Analysis ---
    code_analysis: dict | None  # Serialized CodeAnalysis
    existing_coverage: dict | None  # Serialized CoverageReport
    untested_targets: list[dict]

    # --- Test Generation ---
    test_plan: dict | None  # Serialized TestPlan
    generated_tests: list[dict]  # [{file_path, content, target_class, test_methods}]

    # --- Execution ---
    test_results: list[dict]  # [{test_name, passed, error_message}]
    new_coverage: dict | None

    # --- Reflexion ---
    iteration: int
    critic_feedback: str | None
    tests_to_fix: list[dict]

    # --- Output ---
    report: dict | None  # Serialized RunReport

    # --- LLM Tracking ---
    messages: Annotated[list, add_messages]

    # --- Status ---
    current_step: str
    error: str | None
