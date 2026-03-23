"""Prompts for the test generator node."""

import json

GENERATOR_SYSTEM_PROMPT = """You are an expert test engineer. Your job is to generate high-quality, \
compilable test cases for code that lacks test coverage.

CRITICAL RULES — violations cause compilation failures:
1. NEVER access private or package-private fields directly. Use ONLY public methods to test behavior.
2. ALWAYS include the correct package declaration matching the file path.
   Example: file at src/test/java/com/demo/agent/common/FooTest.java → package com.demo.agent.common;
3. ALWAYS include all necessary imports.
4. Use the appropriate test framework (JUnit 5 + Mockito for Java, pytest for Python).
5. Each test must have clear arrange/act/assert sections.
6. Use descriptive test method names that explain what is being tested.
7. Mock external dependencies using @Mock and @InjectMocks — tests must be isolated.
8. For Java: use @ExtendWith(MockitoExtension.class), NOT @SpringBootTest.
9. For Java with Lombok: the class may use @RequiredArgsConstructor — create instances via constructor.
10. Include edge cases and boundary values.
11. Test through public API only. If you need to verify internal state, call a public getter or method.
12. For classes with no dependencies (POJOs, utility classes), instantiate directly — no mocking needed.
13. CAREFULLY read the source code to understand what each method ACTUALLY returns before writing assertions.
    Do NOT assume a method returns a count when it returns a ratio. Read the implementation.
14. If a class has no public getter for a field, test the field INDIRECTLY through methods that use it.
    Example: if there's no getTotalInvestigations(), test by calling startInvestigation() then checking getAverageToolCalls() with the right expected value.

Output format: Return a JSON array of test files, each with:
{
    "file_path": "src/test/java/com/app/service/MyServiceTest.java",
    "content": "// full test file content — MUST start with package declaration",
    "target_class": "MyService",
    "test_methods": ["testMethod1", "testMethod2"],
    "framework": "junit5"
}

IMPORTANT: Return ONLY the JSON array, no markdown formatting."""


def build_generation_prompt(
    code_analysis: dict,
    existing_coverage: dict,
    pr_diff: dict,
    critic_feedback: str | None = None,
    tests_to_fix: list[dict] | None = None,
    previous_tests: list[dict] | None = None,
) -> str:
    """Build the user prompt for test generation."""
    parts = []

    # PR context
    parts.append(f"## PR: {pr_diff.get('title', 'Unknown')}")
    parts.append(f"Description: {pr_diff.get('description', 'No description')}\n")

    # Changed files with patches
    parts.append("## Changed Files")
    for f in pr_diff.get("files", []):
        parts.append(f"\n### {f['path']} ({f.get('status', 'modified')})")
        parts.append(f"Lines added: {f.get('lines_added', 0)}")
        if f.get("patch"):
            parts.append(f"```diff\n{f['patch']}\n```")

    # Code analysis
    parts.append("\n## Code Analysis")
    for file_analysis in code_analysis.get("files", []):
        parts.append(f"\n### {file_analysis['file_path']}")
        for cls in file_analysis.get("classes", []):
            parts.append(f"Class: {cls['name']}")
            parts.append(f"  Dependencies: {', '.join(cls.get('dependencies', []))}")
            parts.append(f"  Annotations: {', '.join(cls.get('annotations', []))}")
            for method in cls.get("methods", []):
                status = ""
                if method.get("is_new"):
                    status = " [NEW]"
                elif method.get("is_modified"):
                    status = " [MODIFIED]"
                parts.append(
                    f"  - {method['name']}({', '.join(p.get('type', '') for p in method.get('parameters', []))})"
                    f" → {method.get('return_type', 'void')}"
                    f" (complexity: {method.get('complexity', 1)}){status}"
                )
        parts.append(f"  Imports: {', '.join(file_analysis.get('imports', []))}")

    # Coverage gaps
    parts.append("\n## Existing Coverage Gaps")
    for file_path, cov in existing_coverage.get("files", {}).items():
        parts.append(f"\n### {file_path}")
        parts.append(f"Line coverage: {cov.get('line_rate', 0):.0%}")
        parts.append(f"Uncovered methods: {', '.join(cov.get('uncovered_methods', []))}")
        parts.append("Uncovered branches:")
        for branch in cov.get("uncovered_branches", []):
            parts.append(f"  - {branch}")

    # Risk areas
    risk_areas = code_analysis.get("risk_areas", [])
    if risk_areas:
        parts.append("\n## Risk Areas (prioritize tests for these)")
        for area in risk_areas:
            parts.append(f"  - [{area.get('level', 'medium')}] {area.get('area', '')}: {area.get('reason', '')}")

    # Reflexion context (if retrying)
    if critic_feedback and tests_to_fix:
        parts.append("\n## REFLEXION — Fix These Failing Tests")
        parts.append(f"Feedback: {critic_feedback}")
        parts.append("\nTests to fix:")
        for test in tests_to_fix:
            parts.append(f"  - {test.get('test_name', '')}: {test.get('error_message', '')}")
        parts.append(
            "\nIMPORTANT: Return the COMPLETE test file with ALL tests — both the passing "
            "tests (unchanged) and the fixed versions of the failing tests. "
            "Do NOT return only the failing tests — the output replaces the entire file."
        )

    # Include previous generated tests in reflexion mode so LLM can preserve passing tests
    if critic_feedback and previous_tests:
        parts.append("\n## Previously Generated Test File (include passing tests from this)")
        for test in previous_tests:
            parts.append(f"\n### {test.get('file_path', '')}")
            content = test.get('content', '')
            if len(content) > 3000:
                content = content[:3000] + "\n// ... truncated"
            parts.append(f"```java\n{content}\n```")

    parts.append(
        "\n## Task\n"
        "Generate test files that cover the uncovered branches listed above. "
        "Focus on the highest-priority risk areas first."
    )

    return "\n".join(parts)
