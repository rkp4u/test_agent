"""Base class for language-specific AST handlers."""

from abc import ABC, abstractmethod

from agent_forge.models.analysis import ClassInfo, FileAnalysis, FunctionSignature


class LanguageHandler(ABC):
    """Abstract base for language-specific code analysis."""

    @abstractmethod
    def extract_classes(self, source: bytes, file_path: str) -> list[ClassInfo]:
        """Extract class definitions with their methods."""
        ...

    @abstractmethod
    def extract_functions(self, source: bytes, file_path: str) -> list[FunctionSignature]:
        """Extract top-level function/method signatures."""
        ...

    @abstractmethod
    def extract_imports(self, source: bytes) -> list[str]:
        """Extract import statements."""
        ...

    @abstractmethod
    def extract_package(self, source: bytes) -> str:
        """Extract package/module name."""
        ...
