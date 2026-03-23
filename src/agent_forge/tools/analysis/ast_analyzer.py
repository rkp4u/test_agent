"""AST analyzer — cross-references tree-sitter analysis with PR diffs."""

import logging
from pathlib import Path

from agent_forge.models.analysis import ClassInfo, CodeAnalysis, FileAnalysis, FunctionSignature
from agent_forge.models.enums import Language
from agent_forge.tools.analysis.languages.base import LanguageHandler
from agent_forge.tools.analysis.languages.java import JavaHandler

logger = logging.getLogger(__name__)

# Registry of language handlers
_HANDLERS: dict[Language, LanguageHandler] = {}


def get_handler(language: Language) -> LanguageHandler | None:
    """Get or create a handler for the given language."""
    if language not in _HANDLERS:
        if language == Language.JAVA:
            _HANDLERS[language] = JavaHandler()
        # Phase 3+: Add Python, TypeScript handlers
        else:
            return None
    return _HANDLERS.get(language)


class ASTAnalyzer:
    """Analyzes source code using tree-sitter and cross-references with PR diffs."""

    def analyze_file(
        self,
        source: str | bytes,
        file_path: str,
        language: Language,
        changed_lines: set[int] | None = None,
    ) -> FileAnalysis | None:
        """Analyze a single source file.

        Args:
            source: File content (str or bytes)
            file_path: Path relative to repo root
            language: Programming language
            changed_lines: Set of line numbers that were changed in the PR diff.
                          Used to mark functions as new/modified.
        """
        handler = get_handler(language)
        if handler is None:
            logger.warning(f"No handler for language {language}, skipping {file_path}")
            return None

        if isinstance(source, str):
            source = source.encode("utf-8")

        try:
            classes = handler.extract_classes(source, file_path)
            imports = handler.extract_imports(source)
            package = handler.extract_package(source)

            # Cross-reference with diff to mark changed functions
            if changed_lines:
                self._mark_changed_functions(classes, changed_lines)

            # Flatten all functions
            all_functions = []
            for cls in classes:
                all_functions.extend(cls.methods)

            total_lines = source.count(b"\n") + 1

            return FileAnalysis(
                file_path=file_path,
                language=language,
                classes=classes,
                functions=all_functions,
                imports=imports,
                total_lines=total_lines,
                changed_lines=len(changed_lines) if changed_lines else 0,
            )

        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return None

    def analyze_files(
        self,
        files: list[dict],
        file_contents: dict[str, str],
    ) -> CodeAnalysis:
        """Analyze multiple files from a PR diff.

        Args:
            files: List of file change dicts from PR diff (with path, language, hunks/patch)
            file_contents: Map of file_path → source content (fetched from GitHub)
        """
        file_analyses = []
        all_risk_areas = []
        all_untested = []

        for file_info in files:
            path = file_info["path"]
            lang_str = file_info.get("language", "unknown")

            # Determine language
            if isinstance(lang_str, str):
                try:
                    language = Language(lang_str)
                except ValueError:
                    ext = Path(path).suffix
                    language = Language.from_extension(ext)
            else:
                language = lang_str

            # Skip unsupported languages and deleted files
            if language == Language.UNKNOWN:
                logger.info(f"Skipping unsupported file: {path}")
                continue

            status = file_info.get("status", "modified")
            if status == "deleted":
                continue

            source = file_contents.get(path)
            if not source:
                logger.warning(f"No content available for {path}, skipping")
                continue

            # Extract changed line numbers from hunks or patch
            changed_lines = self._extract_changed_lines(file_info)

            analysis = self.analyze_file(source, path, language, changed_lines)
            if analysis:
                file_analyses.append(analysis)

                # Identify risk areas (high complexity + changed)
                for fn in analysis.functions:
                    if (fn.is_new or fn.is_modified) and fn.complexity >= 3:
                        all_risk_areas.append({
                            "area": f"{fn.class_name}.{fn.name}" if fn.class_name else fn.name,
                            "reason": f"Complexity {fn.complexity}, "
                                      f"{'new' if fn.is_new else 'modified'} in this PR",
                            "level": "high" if fn.complexity >= 5 else "medium",
                        })

                    # All new/modified functions without tests are untested targets
                    if fn.is_new or fn.is_modified:
                        all_untested.append({
                            "file_path": path,
                            "class_name": fn.class_name,
                            "method_name": fn.name,
                            "return_type": fn.return_type,
                            "parameters": fn.parameters,
                            "complexity": fn.complexity,
                            "annotations": fn.annotations,
                            "priority": "high" if fn.complexity >= 3 else "medium",
                        })

        total_branches = sum(
            fn.complexity
            for fa in file_analyses
            for fn in fa.functions
            if fn.is_new or fn.is_modified
        )

        return CodeAnalysis(
            files=file_analyses,
            total_branches=total_branches,
            risk_areas=all_risk_areas,
            untested_targets=all_untested,
        )

    def _mark_changed_functions(
        self, classes: list[ClassInfo], changed_lines: set[int]
    ) -> None:
        """Mark functions as new or modified based on diff line numbers."""
        for cls in classes:
            for method in cls.methods:
                method_lines = set(range(method.line_start, method.line_end + 1))
                overlap = method_lines & changed_lines

                if overlap:
                    # If most of the method is new, mark as new
                    overlap_ratio = len(overlap) / len(method_lines) if method_lines else 0
                    if overlap_ratio > 0.8:
                        method.is_new = True
                    else:
                        method.is_modified = True

    def _extract_changed_lines(self, file_info: dict) -> set[int]:
        """Extract added/modified line numbers from file change info."""
        changed = set()

        # If we have parsed hunks
        hunks = file_info.get("hunks", [])
        for hunk in hunks:
            for line_num, _ in hunk.get("added_lines", []):
                changed.add(line_num)

        # If we only have a raw patch, parse line numbers from it
        if not changed and file_info.get("patch"):
            patch = file_info["patch"]
            current_new_line = 0

            for line in patch.split("\n"):
                if line.startswith("@@"):
                    # Parse @@ -old,count +new,count @@
                    try:
                        parts = line.split("@@")[1].strip()
                        new_part = parts.split(" ")[1]
                        current_new_line = int(new_part.split(",")[0].lstrip("+"))
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("+") and not line.startswith("+++"):
                    changed.add(current_new_line)
                    current_new_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    pass  # Removed lines don't get a new line number
                else:
                    current_new_line += 1

        # If it's a new file, all lines are changed
        if file_info.get("status") in ("added", "ADDED"):
            lines_added = file_info.get("lines_added", 0)
            if lines_added > 0:
                changed = set(range(1, lines_added + 1))

        return changed
