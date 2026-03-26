"""Safe mutation injection with guaranteed file restoration."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


class MutationInjectionError(Exception):
    """Raised when a mutation cannot be applied to the source file."""


class MutationInjector:
    """Injects code mutations into source files and guarantees restoration.

    Uses string replacement (original_code → mutated_code) rather than line
    numbers, which is more robust against minor formatting drift.

    Usage:
        injector = MutationInjector(Path("/path/to/repo"))
        with injector.inject_mutant(mutant_dict) as success:
            if success:
                # run tests — file is mutated
                ...
            # file is restored automatically on context exit
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._backups: dict[Path, str] = {}

    @contextmanager
    def inject_mutant(self, mutant: dict) -> Generator[bool, None, None]:
        """Context manager that injects a mutation and guarantees restoration.

        Yields True if injection succeeded, False if original_code not found.
        Restoration always runs in the finally block.
        """
        file_path = self.repo_path / mutant["file_path"]

        if not file_path.exists():
            logger.warning(f"Mutant target file not found: {file_path}")
            yield False
            return

        original_content = file_path.read_text(encoding="utf-8")
        original_code = mutant["original_code"]
        mutated_code = mutant["mutated_code"]

        if original_code not in original_content:
            logger.warning(
                f"Mutant {mutant['mutant_id']}: original_code snippet not found in {mutant['file_path']}"
            )
            yield False
            return

        self._backups[file_path] = original_content

        try:
            mutated_content = original_content.replace(original_code, mutated_code, 1)
            file_path.write_text(mutated_content, encoding="utf-8")
            logger.debug(
                f"Injected mutant {mutant['mutant_id']} into {mutant['file_path']} "
                f"({mutant['mutation_type']})"
            )
            yield True
        finally:
            self._restore(file_path)

    def _restore(self, file_path: Path) -> None:
        """Restore a single file to its original content."""
        if file_path in self._backups:
            file_path.write_text(self._backups.pop(file_path), encoding="utf-8")
            logger.debug(f"Restored {file_path.name}")

    def restore_all(self) -> None:
        """Emergency restore for all backed-up files.

        Call this in outer exception handlers to ensure no mutated files remain.
        """
        if not self._backups:
            return
        logger.warning(f"Emergency restore: restoring {len(self._backups)} file(s)")
        for file_path, content in list(self._backups.items()):
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Emergency restored: {file_path.name}")
        self._backups.clear()

    def verify_restoration(self) -> bool:
        """Returns True if all backups have been properly restored."""
        return len(self._backups) == 0
