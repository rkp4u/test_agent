"""Report models for agent output."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CoverageComparison:
    file_path: str
    before_line_rate: float
    after_line_rate: float
    before_branch_rate: float
    after_branch_rate: float

    @property
    def line_delta(self) -> float:
        return self.after_line_rate - self.before_line_rate

    @property
    def branch_delta(self) -> float:
        return self.after_branch_rate - self.before_branch_rate


@dataclass
class TestResult:
    test_name: str
    passed: bool
    error_message: str | None = None
    duration_ms: float = 0.0


@dataclass
class RunReport:
    """Final structured report from the agent."""

    # Metadata
    repo: str
    pr_number: int
    pr_title: str
    timestamp: datetime = field(default_factory=datetime.now)
    run_id: str = ""

    # Analysis
    files_analyzed: list[str] = field(default_factory=list)
    methods_found: int = 0
    uncovered_methods: int = 0

    # Generation
    tests_generated: int = 0
    test_files_created: list[str] = field(default_factory=list)

    # Execution
    tests_passed: int = 0
    tests_failed: int = 0
    test_results: list[TestResult] = field(default_factory=list)
    iterations_used: int = 1

    # Coverage
    coverage_before: float = 0.0
    coverage_after: float = 0.0
    coverage_comparisons: list[CoverageComparison] = field(default_factory=list)

    # Summary
    tool_calls: int = 0
    suggestions: list[str] = field(default_factory=list)

    @property
    def coverage_delta(self) -> float:
        return self.coverage_after - self.coverage_before

    @property
    def all_tests_passed(self) -> bool:
        return self.tests_failed == 0
