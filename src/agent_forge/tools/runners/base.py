"""Base test runner interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestRunResult:
    """Result of running tests."""

    total_run: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    test_results: list[dict] = field(default_factory=list)  # [{test_name, passed, error_message}]
    stdout: str = ""
    stderr: str = ""
    success: bool = False  # True if build + tests completed without errors


class BaseTestRunner(ABC):
    """Abstract base for test runners."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    @abstractmethod
    async def run_tests(
        self, test_files: list[Path] | None = None, timeout: int = 300
    ) -> TestRunResult:
        """Run tests and return results."""
        ...

    @abstractmethod
    async def write_test_file(self, relative_path: str, content: str) -> Path:
        """Write a test file to the correct location in the repo."""
        ...
