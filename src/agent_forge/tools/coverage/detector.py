"""Build tool and coverage configuration detector."""

import logging

from agent_forge.models.enums import BuildTool, Language, TestFramework

logger = logging.getLogger(__name__)


async def detect_build_tool(client, owner: str, repo: str, ref: str) -> dict:
    """Detect the build tool and test configuration from repo files.

    Returns dict with: build_tool, test_framework, has_jacoco, source_dir, test_dir
    """
    result = {
        "build_tool": BuildTool.UNKNOWN,
        "test_framework": TestFramework.UNKNOWN,
        "has_coverage": False,
        "coverage_tool": None,
        "primary_language": Language.UNKNOWN,
    }

    # Check for Gradle
    try:
        build_gradle = await client.get_file_content(owner, repo, "build.gradle.kts", ref)
        result["build_tool"] = BuildTool.GRADLE
        _analyze_gradle(build_gradle, result)
        return result
    except Exception:
        pass

    try:
        build_gradle = await client.get_file_content(owner, repo, "build.gradle", ref)
        result["build_tool"] = BuildTool.GRADLE
        _analyze_gradle(build_gradle, result)
        return result
    except Exception:
        pass

    # Check for Maven
    try:
        pom = await client.get_file_content(owner, repo, "pom.xml", ref)
        result["build_tool"] = BuildTool.MAVEN
        _analyze_maven(pom, result)
        return result
    except Exception:
        pass

    # Check for Python
    try:
        pyproject = await client.get_file_content(owner, repo, "pyproject.toml", ref)
        result["build_tool"] = BuildTool.PIP
        result["primary_language"] = Language.PYTHON
        result["test_framework"] = TestFramework.PYTEST
        if "pytest-cov" in pyproject or "coverage" in pyproject:
            result["has_coverage"] = True
            result["coverage_tool"] = "coverage.py"
        return result
    except Exception:
        pass

    logger.warning("Could not detect build tool")
    return result


def _analyze_gradle(content: str, result: dict) -> None:
    """Analyze build.gradle(.kts) for test and coverage config."""
    result["primary_language"] = Language.JAVA

    # Detect test framework
    if "junit-jupiter" in content or "junit5" in content.lower():
        result["test_framework"] = TestFramework.JUNIT5
    elif "testng" in content.lower():
        result["test_framework"] = TestFramework.TESTNG
    else:
        result["test_framework"] = TestFramework.JUNIT5  # Default for Gradle

    # Detect JaCoCo
    if "jacoco" in content.lower():
        result["has_coverage"] = True
        result["coverage_tool"] = "jacoco"

    # Detect Kotlin
    if "kotlin" in content.lower():
        result["primary_language"] = Language.KOTLIN


def _analyze_maven(content: str, result: dict) -> None:
    """Analyze pom.xml for test and coverage config."""
    result["primary_language"] = Language.JAVA

    # Detect test framework
    if "junit-jupiter" in content or "junit5" in content.lower():
        result["test_framework"] = TestFramework.JUNIT5
    else:
        result["test_framework"] = TestFramework.JUNIT5  # Default for Maven

    # Detect JaCoCo
    if "jacoco" in content.lower():
        result["has_coverage"] = True
        result["coverage_tool"] = "jacoco"
