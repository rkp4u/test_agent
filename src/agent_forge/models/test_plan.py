"""Test plan and generated test models."""

from dataclasses import dataclass, field


@dataclass
class TestTarget:
    """A specific function/method that needs test coverage."""

    file_path: str
    class_name: str | None
    method_name: str
    uncovered_branches: list[str] = field(default_factory=list)
    priority: str = "medium"  # low, medium, high
    reason: str = ""


@dataclass
class TestCase:
    """A planned or generated test case."""

    test_name: str
    target_method: str
    target_branch: str
    description: str
    test_code: str = ""
    file_path: str = ""  # Where to write the test
    assertions: int = 0
    passed: bool | None = None  # None = not run yet
    error_message: str | None = None


@dataclass
class TestPlan:
    """The overall plan for test generation."""

    targets: list[TestTarget] = field(default_factory=list)
    planned_tests: list[TestCase] = field(default_factory=list)
    estimated_coverage_increase: str = ""
    strategy: str = ""  # Description of the approach


@dataclass
class GeneratedTest:
    """A test file ready to be written to disk."""

    file_path: str  # Full path where to write (e.g., src/test/java/...)
    content: str  # Full file content
    target_class: str
    test_methods: list[str] = field(default_factory=list)
    framework: str = "junit5"
