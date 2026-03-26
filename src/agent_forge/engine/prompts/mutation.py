"""Prompt templates for mutation testing pipeline."""

import json


# ---------------------------------------------------------------------------
# Mutation Generator prompts
# ---------------------------------------------------------------------------

MUTATION_GENERATOR_SYSTEM_PROMPT = """You are a senior software engineer generating realistic code mutations (bugs) for mutation testing.

Your goal is to create mutations that simulate bugs a real developer might accidentally introduce — not trivial syntax errors.

## Rules
1. Each mutation must be a SMALL, LOCALIZED change (1-5 lines max).
2. Mutations must produce COMPILABLE code (no syntax errors).
3. Focus on SEMANTIC bugs — wrong logic, not wrong syntax.
4. Generate 2-3 mutations per changed method, capped at 12 total.
5. Use the EXACT source code snippet for original_code (must match character-for-character).
6. Each original_code snippet must be UNIQUE within the file.
7. Include enough surrounding context in the snippet to guarantee uniqueness.

## Mutation Types to Use
- off_by_one: Change boundary conditions (< to <=, > to >=, +1/-1)
- wrong_operator: Flip operators (&& to ||, + to -, * to /)
- missing_null_check: Remove a null/empty check
- swapped_args: Swap two method arguments of the same type
- wrong_return: Return wrong value (true/false, null, wrong field)
- missing_boundary: Remove range/min/max checks
- wrong_exception: Throw wrong exception type, or swallow exception
- wrong_condition: Negate or invert a condition

## Output Format
Return a JSON array only. No prose. No markdown code blocks. No explanations outside JSON.

[
  {
    "mutant_id": "M001",
    "file_path": "src/main/java/com/example/Service.java",
    "original_code": "if (count >= maxRetries) {",
    "mutated_code": "if (count > maxRetries) {",
    "mutation_description": "Off-by-one: allows one extra retry attempt by using > instead of >=",
    "mutation_type": "off_by_one",
    "line_start": 42,
    "line_end": 42
  }
]"""


def build_mutation_prompt(
    code_analysis: dict,
    pr_diff: dict,
    file_contents: dict[str, str],
) -> str:
    """Build user prompt for mutation generation."""
    parts = ["# PR Context\n"]

    pr_title = pr_diff.get("title", "Unknown PR")
    changed_paths = [f.get("path", "") for f in pr_diff.get("files", [])]
    parts.append(f"PR Title: {pr_title}")
    parts.append(f"Changed files: {', '.join(changed_paths)}\n")

    # Full source code for each changed file
    parts.append("# Source Code of Changed Files\n")
    for file_path, content in file_contents.items():
        parts.append(f"## {file_path}\n```java\n{content}\n```\n")

    # Diff patches for context
    parts.append("# PR Diff (changed lines only)\n")
    for f in pr_diff.get("files", []):
        patch = f.get("patch", "")
        if patch:
            parts.append(f"### {f.get('path', '')}\n```diff\n{patch}\n```\n")

    # AST analysis — methods and complexity
    parts.append("# Code Analysis (AST)\n")
    files_analysis = code_analysis.get("files", [])
    for fa in files_analysis:
        parts.append(f"## {fa.get('file_path', '')}")
        for cls in fa.get("classes", []):
            parts.append(f"  Class: {cls.get('name', '')}")
            for method in cls.get("methods", []):
                changed = " [CHANGED]" if method.get("is_new") or method.get("is_modified") else ""
                parts.append(
                    f"    - {method.get('name', '')}({', '.join(p.get('type', '') for p in method.get('parameters', []))})"
                    f" → {method.get('return_type', 'void')}"
                    f" complexity={method.get('complexity', 1)}{changed}"
                )

    parts.append(
        "\n# Task\nGenerate up to 12 realistic mutations targeting the CHANGED methods marked [CHANGED]."
        " Prioritize methods with higher complexity."
        " Return JSON array only."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Equivalence Detector prompts
# ---------------------------------------------------------------------------

EQUIVALENCE_JUDGE_SYSTEM_PROMPT = """You are a formal reasoning expert classifying code mutations as equivalent or non-equivalent.

An EQUIVALENT mutation produces IDENTICAL observable behavior to the original code in all possible executions.
A NON-EQUIVALENT mutation produces DIFFERENT observable behavior in at least one execution path.

## Examples of EQUIVALENT mutations
- Changing `x >= 0` to `x > -1` for integer x (same behavior)
- Reordering independent assignments: `a = 1; b = 2;` → `b = 2; a = 1;`
- `return true;` → `return Boolean.TRUE;`

## Examples of NON-EQUIVALENT mutations
- Changing `count >= maxRetries` to `count > maxRetries` (allows one extra iteration)
- Changing `&&` to `||` in a condition
- Removing a null check before method call
- Swapping arguments to a method

## Output Format
Return a JSON array only. One entry per mutant. No prose.

[
  {
    "mutant_id": "M001",
    "verdict": "non_equivalent",
    "confidence": 0.95,
    "reason": "Changes boundary condition allowing one extra retry"
  }
]"""


def build_equivalence_prompt(mutants: list[dict]) -> str:
    """Build user prompt for equivalence detection."""
    parts = ["# Mutants to Classify\n"]
    parts.append("For each mutant, determine if it is equivalent or non-equivalent to the original.\n")

    for m in mutants:
        parts.append(f"## {m['mutant_id']} — {m['mutation_type']}")
        parts.append(f"File: {m['file_path']}")
        parts.append(f"Description: {m['mutation_description']}")
        parts.append(f"\nOriginal:\n```java\n{m['original_code']}\n```")
        parts.append(f"\nMutated:\n```java\n{m['mutated_code']}\n```\n")

    parts.append("Return JSON array with verdict for each mutant_id.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Killing Test Generator prompts
# ---------------------------------------------------------------------------

KILLING_TEST_SYSTEM_PROMPT = """You are an expert Java test engineer writing tests that detect specific bugs.

You will be given:
1. A description of a specific bug (mutation) in the code
2. The original (correct) code snippet
3. The mutated (buggy) code snippet
4. FULL SOURCE CODE of the target class (use this for exact method signatures and imports)

Your task: Write a JUnit 5 test that:
- PASSES when run against the original (correct) code
- FAILS when run against the mutated (buggy) code

## Critical Rules
1. The test MUST pass on the original code — it cannot break working behavior.
2. The test MUST fail on the buggy code — it must specifically detect this bug.
3. Never access private fields or methods — use only public API.
4. ALWAYS include ALL required imports from the full source code (especially java.util, java.util.concurrent, etc).
5. Study the FULL SOURCE CODE section to determine EXACT method signatures and constructor parameters.
6. Copy the package declaration from the full source code — do NOT guess.
7. Use JUnit 5. Arrange/Act/Assert pattern. No Mockito unless class has Spring dependencies.
8. The assertion must directly validate the behavior that the mutation breaks.
9. Test class name: <TargetClass>MutationTest.

## Avoiding Compilation Errors
- ONLY call methods with ZERO parameters if source shows `public X methodName()` (no params)
- If source shows `public X methodName(String s, int i)`, ALWAYS provide those exact parameters
- If constructor is not shown or uses Spring @Component, use no-arg constructor
- Never import classes that don't exist (e.g., don't use `Map.Entry` without importing `java.util.*`)
- Copy constructor invocation EXACTLY as shown in source code examples

## Output Format
Return a JSON array. One test file per surviving mutant. No prose.

[
  {
    "file_path": "src/test/java/com/example/ServiceMutationTest.java",
    "content": "package com.example;\\n\\nimport org.junit.jupiter.api.Test;\\n\\npublic class ServiceMutationTest { ... }",
    "target_class": "Service",
    "test_methods": ["testRetryLimitEnforced_M001"],
    "target_mutant_id": "M001",
    "framework": "junit5"
  }
]"""


def build_killing_test_prompt(
    surviving_mutants: list[dict],
    code_analysis: dict,
    critic_feedback: str | None = None,
    tests_to_fix: list[dict] | None = None,
    previous_tests: list[dict] | None = None,
    file_contents: dict[str, str] | None = None,
) -> str:
    """Build user prompt for killing test generation.

    CRITICAL: Include full source code of target classes to help LLM understand:
    - Class structure, constructors, fields
    - Dependencies and how to inject them
    - Package declaration and required imports
    - Public API surface area
    """
    parts = []

    if critic_feedback and tests_to_fix:
        parts.append("# Reflexion: Fix These Failing Killing Tests\n")
        parts.append(f"Feedback:\n{critic_feedback}\n")
        parts.append("Tests to regenerate:")
        for t in (tests_to_fix or []):
            parts.append(f"  - {t.get('test_name', '')}: {t.get('failure_type', '')} — {t.get('error_message', '')}")
        parts.append("")

    parts.append("# Surviving Mutants — Write Killing Tests\n")
    parts.append(
        "Each test must PASS on original code and FAIL on the mutated (buggy) code.\n"
    )

    # Collect unique files that contain the mutants
    mutant_files = {}
    target_ids = {t.get("mutant_id") for t in (tests_to_fix or [])} if tests_to_fix else None

    for m in surviving_mutants:
        if target_ids and m["mutant_id"] not in target_ids:
            continue
        mutant_files[m['file_path']] = m

    # Include FULL SOURCE CODE for all target files (crucial for test generation)
    if file_contents:
        parts.append("# Full Source Code of Target Classes\n")
        parts.append("⚠️  COPY imports and method signatures EXACTLY as shown below.\n")
        parts.append("Do NOT guess or simplify method signatures.\n\n")
        for file_path, content in file_contents.items():
            # Only include files with mutants
            if any(m['file_path'] == file_path for m in surviving_mutants):
                parts.append(f"## {file_path}\n```java\n{content}\n```\n")

                # Extract and highlight key parts for clarity
                lines = content.split('\n')
                imports = [l for l in lines if l.strip().startswith('import ')]
                if imports:
                    parts.append(f"**Imports needed:**\n")
                    for imp in imports[:10]:  # Show first 10 imports
                        parts.append(f"  {imp.strip()}")
                    parts.append("")

    # Now show each specific mutant with context
    parts.append("# Mutants Requiring Killing Tests\n")
    for m in surviving_mutants:
        if target_ids and m["mutant_id"] not in target_ids:
            continue
        parts.append(f"## {m['mutant_id']} — {m['mutation_description']}")
        parts.append(f"File: {m['file_path']}")
        parts.append(f"Mutation type: {m['mutation_type']}")
        parts.append(f"\nOriginal (correct) code:\n```java\n{m['original_code']}\n```")
        parts.append(f"\nMutated (buggy) code:\n```java\n{m['mutated_code']}\n```")

        # Behavioral difference
        diff_lines = []
        orig_lines = m["original_code"].splitlines()
        mut_lines = m["mutated_code"].splitlines()
        for o, mu in zip(orig_lines, mut_lines):
            if o != mu:
                diff_lines.append(f"  Original: {o.strip()}")
                diff_lines.append(f"  Buggy:    {mu.strip()}")
        if diff_lines:
            parts.append("\nBehavioral difference:")
            parts.extend(diff_lines)
        parts.append("")

    # Code analysis context — method signatures and class structure
    parts.append("# Class Structure Reference\n")
    for fa in code_analysis.get("files", []):
        for cls in fa.get("classes", []):
            parts.append(f"\n## Class: {cls.get('name', '')}")
            parts.append(f"Package: {cls.get('package', 'unknown')}")

            # Dependencies for mocking/injection
            deps = cls.get("dependencies", [])
            if deps:
                parts.append(f"Dependencies: {', '.join(deps)}")

            # Constructor info (critical for test setup)
            parts.append("\nConstructor signature:")
            parts.append(f"  {cls.get('name', '')}({', '.join(p.get('type', '') + ' ' + p.get('name', '') for p in cls.get('constructor_params', []))})")

            # Public methods
            parts.append("\nPublic methods:")
            for method in cls.get("methods", []):
                params_str = ', '.join(f"{p.get('type', '')} {p.get('name', '')}" for p in method.get('parameters', []))
                parts.append(
                    f"  {method.get('return_type', 'void')} {method.get('name', '')}({params_str})"
                )

    # Preserve passing tests from previous iteration
    if previous_tests:
        passing_ids = {t.get("target_mutant_id") for t in (tests_to_fix or [])}
        passing_prev = [t for t in previous_tests if t.get("target_mutant_id") not in passing_ids]
        if passing_prev:
            parts.append("\n# Previously Accepted Tests (preserve these unchanged)\n")
            parts.append(json.dumps(passing_prev, indent=2))

    parts.append("\nReturn JSON array of killing test files.")
    return "\n".join(parts)
