"""CLI application — main entry point for agent-forge."""

import asyncio
import logging
import sys
from typing import Optional

import typer
from rich.console import Console

from agent_forge import __version__
from agent_forge.cli.display import (
    console,
    print_error,
    print_header,
    print_report,
    print_step,
    print_step_detail,
    print_step_detail_last,
    print_success,
)
from agent_forge.config.settings import get_settings

app = typer.Typer(
    name="agent-forge",
    help="AI-powered test generation agent — analyzes PR diffs and generates targeted test cases.",
    no_args_is_help=True,
)


def _parse_repo(repo: str) -> str:
    """Normalize repo input to owner/repo format."""
    # Handle full URLs
    if "github.com" in repo:
        parts = repo.rstrip("/").split("/")
        return f"{parts[-2]}/{parts[-1]}"
    # Handle owner/repo format
    if "/" in repo:
        return repo
    # Assume current user's repo
    return repo


@app.command()
def run(
    repo: str = typer.Argument(help="Repository (owner/repo, GitHub URL, or local path)"),
    pr: int = typer.Option(..., "--pr", "-p", help="PR number to analyze"),
    max_iterations: int = typer.Option(3, "--max-iterations", "-m", help="Max reflexion iterations"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Analyze and generate without running tests"),
) -> None:
    """Run the full test generation pipeline: analyze → generate → test → report."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    repo = _parse_repo(repo)

    asyncio.run(_run_pipeline(repo, pr, max_iterations, verbose, dry_run))


async def _run_pipeline(
    repo: str, pr_number: int, max_iterations: int, verbose: bool, dry_run: bool
) -> None:
    """Execute the LangGraph pipeline with Rich progress display."""
    from agent_forge.engine.graph import compile_graph

    settings = get_settings()
    settings.ensure_dirs()

    # Compile the graph
    compiled_graph = compile_graph()

    # Print header
    print_header(repo, pr_number)

    total_steps = 7

    # Initial state
    initial_state = {
        "repo": repo,
        "pr_number": pr_number,
        "repo_local_path": "",
        "pr_diff": None,
        "changed_files": [],
        "code_analysis": None,
        "existing_coverage": None,
        "untested_targets": [],
        "test_plan": None,
        "generated_tests": [],
        "test_results": [],
        "new_coverage": None,
        "iteration": 0,
        "critic_feedback": None,
        "tests_to_fix": [],
        "report": None,
        "messages": [],
        "current_step": "",
        "error": None,
    }

    # Track step completion for display
    step_names = {
        "planner": (1, "Planning"),
        "diff_fetcher": (2, "Fetching PR diff"),
        "code_analyzer": (3, "Analyzing code structure"),
        "coverage_checker": (4, "Checking existing coverage"),
        "test_generator": (5, "Generating tests"),
        "test_runner": (6, "Running tests"),
        "critic": (6, "Evaluating results"),  # Same step number as runner
        "reporter": (7, "Generating report"),
    }

    last_step = ""

    try:
        # Stream through graph execution
        async for event in compiled_graph.astream(initial_state):
            for node_name, node_output in event.items():
                current_step = node_output.get("current_step", node_name)

                if current_step != last_step and current_step in step_names:
                    step_num, description = step_names[current_step]

                    # Mark previous step as done
                    if last_step and last_step in step_names:
                        prev_num, prev_desc = step_names[last_step]

                    # Show current step
                    if current_step == "diff_fetcher":
                        pr_diff = node_output.get("pr_diff", {})
                        files = pr_diff.get("files", [])
                        print_step(step_num, total_steps, f"Fetching PR diff ({len(files)} files changed)", "done")
                        if verbose:
                            for f in files:
                                print_step_detail(
                                    f"{f.get('path', '')} (+{f.get('lines_added', 0)} lines)"
                                )

                    elif current_step == "code_analyzer":
                        analysis = node_output.get("code_analysis", {})
                        files = analysis.get("files", [])
                        total_methods = sum(
                            len(c.get("methods", []))
                            for f in files
                            for c in f.get("classes", [])
                        )
                        new_methods = sum(
                            1
                            for f in files
                            for c in f.get("classes", [])
                            for m in c.get("methods", [])
                            if m.get("is_new") or m.get("is_modified")
                        )
                        print_step(step_num, total_steps, "Analyzing code (tree-sitter)", "done")
                        print_step_detail(f"{new_methods} new/modified methods found")
                        risk_areas = analysis.get("risk_areas", [])
                        if risk_areas:
                            print_step_detail_last(
                                f"Complexity hotspot: {risk_areas[0].get('area', '')}"
                            )

                    elif current_step == "coverage_checker":
                        cov = node_output.get("existing_coverage", {})
                        rate = cov.get("overall_line_rate", 0)
                        gap = cov.get("coverage_gap", "")
                        print_step(step_num, total_steps, "Checking existing coverage", "done")
                        print_step_detail(f"Existing: {rate:.0%} line coverage")
                        if gap:
                            print_step_detail_last(gap)

                    elif current_step == "test_generator":
                        tests = node_output.get("generated_tests", [])
                        total_test_methods = sum(
                            len(t.get("test_methods", [])) for t in tests
                        )
                        iteration = node_output.get("iteration", 0)
                        if iteration and iteration > 0:
                            print_step(
                                step_num, total_steps,
                                f"Regenerating tests (iteration {iteration + 1}/{max_iterations})",
                                "done",
                            )
                        else:
                            print_step(step_num, total_steps, "Generating tests", "done")
                        print_step_detail(f"{len(tests)} test files generated")
                        print_step_detail_last(
                            f"{total_test_methods} test methods targeting uncovered paths"
                        )

                    elif current_step == "test_runner":
                        results = node_output.get("test_results", [])
                        passed = sum(1 for r in results if r.get("passed"))
                        failed = sum(1 for r in results if not r.get("passed"))
                        if failed > 0:
                            print_step(step_num, total_steps, "Running tests", "done")
                            print_step_detail(f"[green]{passed} passed[/], [red]{failed} failed[/]")
                            print_step_detail_last("[yellow]Entering reflexion loop...[/]")
                        else:
                            print_step(step_num, total_steps, "Running tests", "done")
                            print_step_detail(f"[green]{passed} passed[/], 0 failed")
                            print_step_detail_last("[green]All tests passing[/]")

                    elif current_step == "critic":
                        # Critic output is shown inline with test runner
                        pass

                    elif current_step == "reporter":
                        print_step(step_num, total_steps, "Generating report", "done")

                    elif current_step == "planner":
                        print_step(step_num, total_steps, "Planning", "done")

                    last_step = current_step

                # Check for final report
                report = node_output.get("report")
                if report:
                    print_report(report)

    except Exception as e:
        print_error(f"Pipeline failed: {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def analyze(
    repo: str = typer.Argument(help="Repository (owner/repo or URL)"),
    pr: int = typer.Option(..., "--pr", "-p", help="PR number"),
) -> None:
    """Analyze a PR without generating tests — shows diff, code structure, and coverage gaps."""
    console.print("[yellow]analyze command coming in Phase 2[/]")


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"agent-forge v{__version__}")


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
