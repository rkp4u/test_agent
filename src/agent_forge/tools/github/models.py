"""GitHub data models."""

from dataclasses import dataclass, field

from agent_forge.models.enums import FileChangeStatus, Language


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)
    context_lines: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class FileChange:
    path: str
    status: FileChangeStatus
    language: Language = Language.UNKNOWN
    old_path: str | None = None
    hunks: list[Hunk] = field(default_factory=list)
    lines_added: int = 0
    lines_deleted: int = 0
    lines_modified: int = 0
    patch: str = ""  # Raw unified diff for this file


@dataclass
class PRDiff:
    pr_number: int
    title: str
    author: str
    base_ref: str
    head_ref: str
    files: list[FileChange] = field(default_factory=list)
    description: str = ""

    @property
    def total_additions(self) -> int:
        return sum(f.lines_added for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.lines_deleted for f in self.files)

    @property
    def changed_file_paths(self) -> list[str]:
        return [f.path for f in self.files]
