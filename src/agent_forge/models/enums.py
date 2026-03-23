"""Enumerations used across the agent."""

from enum import Enum


class Language(str, Enum):
    JAVA = "java"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    KOTLIN = "kotlin"
    GO = "go"
    UNKNOWN = "unknown"

    @classmethod
    def from_extension(cls, ext: str) -> "Language":
        mapping = {
            ".java": cls.JAVA,
            ".py": cls.PYTHON,
            ".ts": cls.TYPESCRIPT,
            ".tsx": cls.TYPESCRIPT,
            ".kt": cls.KOTLIN,
            ".kts": cls.KOTLIN,
            ".go": cls.GO,
        }
        return mapping.get(ext.lower(), cls.UNKNOWN)


class TestFramework(str, Enum):
    JUNIT5 = "junit5"
    PYTEST = "pytest"
    JEST = "jest"
    TESTNG = "testng"
    UNKNOWN = "unknown"


class BuildTool(str, Enum):
    GRADLE = "gradle"
    MAVEN = "maven"
    PIP = "pip"
    NPM = "npm"
    UNKNOWN = "unknown"


class FileChangeStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class FailureType(str, Enum):
    COMPILATION = "compilation"
    RUNTIME = "runtime"
    ASSERTION = "assertion"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
