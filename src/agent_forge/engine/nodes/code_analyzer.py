"""Code analyzer node — analyzes code structure using tree-sitter AST parsing."""

import logging
from dataclasses import asdict, field

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.tools.analysis.ast_analyzer import ASTAnalyzer
from agent_forge.tools.github.client import GitHubClient

logger = logging.getLogger(__name__)


def _serialize_analysis(analysis) -> dict:
    """Convert CodeAnalysis to a serializable dict."""
    files = []
    for fa in analysis.files:
        classes = []
        for cls in fa.classes:
            methods = []
            for m in cls.methods:
                methods.append({
                    "name": m.name,
                    "class_name": m.class_name,
                    "return_type": m.return_type,
                    "parameters": m.parameters,
                    "visibility": m.visibility,
                    "annotations": m.annotations,
                    "line_start": m.line_start,
                    "line_end": m.line_end,
                    "complexity": m.complexity,
                    "is_new": m.is_new,
                    "is_modified": m.is_modified,
                })
            classes.append({
                "name": cls.name,
                "package": cls.package,
                "extends": cls.extends,
                "implements": cls.implements,
                "annotations": cls.annotations,
                "dependencies": cls.dependencies,
                "methods": methods,
            })
        files.append({
            "file_path": fa.file_path,
            "language": fa.language.value,
            "classes": classes,
            "functions": [m for c in classes for m in c["methods"]],
            "imports": fa.imports,
            "total_lines": fa.total_lines,
            "changed_lines": fa.changed_lines,
        })

    return {
        "files": files,
        "total_branches": analysis.total_branches,
        "risk_areas": analysis.risk_areas,
    }


async def code_analyzer_node(state: AgentState) -> dict:
    """Analyze code structure of changed files using tree-sitter.

    Fetches file content from GitHub, parses AST, cross-references with diff
    to identify new/modified functions.
    """
    pr_diff = state.get("pr_diff", {})
    changed_files = state.get("changed_files", [])

    if not pr_diff or not changed_files:
        logger.warning("No PR diff available, returning empty analysis")
        return {
            "current_step": "code_analyzer",
            "code_analysis": {"files": [], "total_branches": 0, "risk_areas": []},
            "untested_targets": [],
        }

    logger.info(f"Analyzing code structure for {len(changed_files)} files")

    # Fetch file contents from GitHub
    settings = get_settings()
    client = GitHubClient(github_token=settings.github_token)

    parts = state["repo"].split("/")
    owner, repo_name = parts[0], parts[1]
    head_ref = pr_diff.get("head_ref", "main")

    file_contents = {}
    files_data = pr_diff.get("files", [])

    for file_info in files_data:
        path = file_info["path"]
        status = file_info.get("status", "modified")

        # Skip deleted files
        if status in ("deleted", "DELETED"):
            continue

        try:
            content = await client.get_file_content(owner, repo_name, path, head_ref)
            file_contents[path] = content
            logger.info(f"  Fetched: {path} ({len(content)} chars)")
        except Exception as e:
            logger.warning(f"  Failed to fetch {path}: {e}")

    # Run AST analysis
    analyzer = ASTAnalyzer()
    analysis = analyzer.analyze_files(files_data, file_contents)

    # Serialize for state
    analysis_dict = _serialize_analysis(analysis)

    # Log summary
    total_new_modified = sum(
        1 for fa in analysis.files
        for fn in fa.functions
        if fn.is_new or fn.is_modified
    )
    logger.info(
        f"Analysis complete: {len(analysis.files)} files, "
        f"{total_new_modified} new/modified methods, "
        f"{len(analysis.risk_areas)} risk areas"
    )

    return {
        "current_step": "code_analyzer",
        "code_analysis": analysis_dict,
        "untested_targets": analysis.untested_targets,
    }
