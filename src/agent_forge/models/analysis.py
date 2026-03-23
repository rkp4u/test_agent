"""Code analysis models."""

from dataclasses import dataclass, field

from agent_forge.models.enums import Language, RiskLevel


@dataclass
class FunctionSignature:
    name: str
    class_name: str | None = None
    parameters: list[dict[str, str]] = field(default_factory=list)  # [{name, type}]
    return_type: str = "void"
    visibility: str = "public"
    annotations: list[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0
    complexity: int = 1
    is_new: bool = False  # True if added in this PR
    is_modified: bool = False  # True if modified in this PR


@dataclass
class ClassInfo:
    name: str
    package: str = ""
    extends: str | None = None
    implements: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    methods: list[FunctionSignature] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # Injected/imported types


@dataclass
class FileAnalysis:
    file_path: str
    language: Language
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionSignature] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    total_lines: int = 0
    changed_lines: int = 0


@dataclass
class CodeAnalysis:
    files: list[FileAnalysis] = field(default_factory=list)
    total_branches: int = 0
    risk_areas: list[dict[str, str]] = field(default_factory=list)  # [{area, reason, level}]
    untested_targets: list[dict] = field(default_factory=list)

    @property
    def total_functions(self) -> int:
        return sum(len(f.functions) for f in self.files)

    @property
    def new_or_modified_functions(self) -> list[FunctionSignature]:
        result = []
        for fa in self.files:
            result.extend(f for f in fa.functions if f.is_new or f.is_modified)
        return result
