"""Gradle test runner — executes tests via ./gradlew."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from agent_forge.tools.runners.base import BaseTestRunner, TestRunResult

logger = logging.getLogger(__name__)


class GradleRunner(BaseTestRunner):
    """Runs tests using the Gradle wrapper."""

    def __init__(self, repo_path: Path):
        super().__init__(repo_path)
        self.wrapper = repo_path / "gradlew"

        if not self.wrapper.exists():
            raise FileNotFoundError(f"Gradle wrapper not found at {self.wrapper}")

        # Ensure executable
        self.wrapper.chmod(0o755)

    async def write_test_file(self, relative_path: str, content: str) -> Path:
        """Write a test file to the repo's test directory."""
        full_path = self.repo_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.info(f"Wrote test file: {relative_path}")
        return full_path

    async def run_tests(
        self, test_files: list[Path] | None = None, timeout: int = 300
    ) -> TestRunResult:
        """Run tests via ./gradlew test.

        If test_files is provided, only run those specific test classes.
        """
        cmd = [str(self.wrapper), "test", "--no-daemon"]

        # Ensure test files have correct package declarations
        if test_files:
            for tf in test_files:
                self._ensure_package_declaration(tf)

        # Note: we run all tests (no --tests filter) to avoid Gradle resolution issues
        # when package declarations are missing or mismatched

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            success = proc.returncode == 0

            if not success:
                logger.warning(f"Gradle test returned exit code {proc.returncode}")
                # Log key error lines
                for line in stderr.split("\n"):
                    if "FAILED" in line or "error:" in line.lower():
                        logger.warning(f"  {line.strip()}")

            # Parse JUnit XML results
            test_results = self._parse_test_results()

            # If no JUnit results but build failed, extract compilation errors
            if not test_results and not success:
                comp_errors = self._extract_compilation_errors(stderr)
                if comp_errors:
                    test_results = comp_errors

            total = sum(1 for _ in test_results)
            passed = sum(1 for r in test_results if r.get("passed", False))
            failed = sum(1 for r in test_results if not r.get("passed", False) and not r.get("skipped", False))
            skipped = sum(1 for r in test_results if r.get("skipped", False))

            return TestRunResult(
                total_run=total,
                passed=passed,
                failed=failed,
                errors=0,
                skipped=skipped,
                test_results=test_results,
                stdout=stdout,
                stderr=stderr,
                success=success,
            )

        except asyncio.TimeoutError:
            logger.error(f"Test execution timed out after {timeout}s")
            return TestRunResult(
                stdout="",
                stderr=f"Timeout after {timeout}s",
                success=False,
            )

        except Exception as e:
            logger.error(f"Failed to run tests: {e}")
            return TestRunResult(
                stdout="",
                stderr=str(e),
                success=False,
            )

    def _parse_test_results(self) -> list[dict]:
        """Parse JUnit XML test results from build/test-results/test/."""
        results_dir = self.repo_path / "build" / "test-results" / "test"

        if not results_dir.exists():
            logger.warning(f"Test results directory not found: {results_dir}")
            return []

        results = []

        for xml_file in results_dir.glob("TEST-*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()

                for testcase in root.findall("testcase"):
                    test_name = testcase.get("name", "unknown")
                    class_name = testcase.get("classname", "")
                    time_val = float(testcase.get("time", "0"))

                    failure = testcase.find("failure")
                    error = testcase.find("error")
                    skipped_el = testcase.find("skipped")

                    if skipped_el is not None:
                        results.append({
                            "test_name": f"{class_name}.{test_name}",
                            "passed": False,
                            "skipped": True,
                            "duration_ms": time_val * 1000,
                        })
                    elif failure is not None:
                        results.append({
                            "test_name": f"{class_name}.{test_name}",
                            "passed": False,
                            "error_message": failure.get("message", "")[:500],
                            "failure_type": failure.get("type", ""),
                            "duration_ms": time_val * 1000,
                        })
                    elif error is not None:
                        results.append({
                            "test_name": f"{class_name}.{test_name}",
                            "passed": False,
                            "error_message": error.get("message", "")[:500],
                            "failure_type": error.get("type", ""),
                            "duration_ms": time_val * 1000,
                        })
                    else:
                        results.append({
                            "test_name": f"{class_name}.{test_name}",
                            "passed": True,
                            "duration_ms": time_val * 1000,
                        })

            except ET.ParseError as e:
                logger.warning(f"Failed to parse {xml_file}: {e}")

        return results

    def _extract_compilation_errors(self, stderr: str) -> list[dict]:
        """Extract compilation errors from Gradle stderr output."""
        errors = []
        current_file = ""

        for line in stderr.split("\n"):
            line = line.strip()

            # Match lines like: /path/to/File.java:31: error: something
            if ": error:" in line and ".java:" in line:
                error_msg = line.split(": error:")[-1].strip()
                # Extract file and line from the path
                file_part = line.split(": error:")[0]
                file_name = file_part.split("/")[-1].split(":")[0] if "/" in file_part else file_part

                errors.append({
                    "test_name": f"compilation_error_{file_name}_{len(errors)}",
                    "passed": False,
                    "error_message": f"Compilation error in {file_name}: {error_msg}",
                    "failure_type": "compilation",
                })

        # Deduplicate similar errors
        if errors:
            seen = set()
            unique = []
            for e in errors:
                key = e["error_message"]
                if key not in seen:
                    seen.add(key)
                    unique.append(e)
            return unique[:5]  # Cap at 5 to avoid noise

        return []

    def _ensure_package_declaration(self, file_path: Path) -> None:
        """Ensure the test file has the correct package declaration based on its directory."""
        class_name = self._file_to_class_name(file_path)
        if not class_name:
            return

        # Extract package from class name (everything before the last dot)
        parts = class_name.rsplit(".", 1)
        if len(parts) < 2:
            return

        package = parts[0]
        expected_line = f"package {package};"

        try:
            content = file_path.read_text(encoding="utf-8")

            # Check if package declaration exists
            if content.strip().startswith("package "):
                return  # Already has package declaration

            # Prepend package declaration
            content = f"{expected_line}\n\n{content}"
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"  Added package declaration: {expected_line}")

        except Exception as e:
            logger.warning(f"Failed to fix package declaration for {file_path}: {e}")

    def _file_to_class_name(self, file_path: Path) -> str | None:
        """Convert test file path to fully qualified class name."""
        path_str = str(file_path)

        # Handle absolute and relative paths
        for prefix in ("src/test/java/", "src/test/kotlin/"):
            idx = path_str.find(prefix)
            if idx >= 0:
                relative = path_str[idx + len(prefix):]
                # Remove .java/.kt extension and convert / to .
                class_name = relative.removesuffix(".java").removesuffix(".kt").replace("/", ".")
                return class_name

        return None
