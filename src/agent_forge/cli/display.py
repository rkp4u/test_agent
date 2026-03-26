"""Rich console display for agent output."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich.layout import Layout

console = Console()


def print_header(repo: str, pr_number: int, pr_title: str = "") -> None:
    """Print the agent header panel."""
    title_text = f"[bold green]Agent Forge[/] — Test Generation"
    content = f"[dim]Repository:[/] {repo}\n[dim]PR:[/] #{pr_number}"
    if pr_title:
        content += f" — {pr_title}"

    console.print(Panel(content, title=title_text, border_style="green"))
    console.print()


def print_step(step_num: int, total: int, description: str, status: str = "running") -> None:
    """Print a workflow step with status indicator."""
    icons = {
        "running": "[yellow]⏳[/]",
        "done": "[green]✓[/]",
        "failed": "[red]✗[/]",
        "skipped": "[dim]○[/]",
    }
    icon = icons.get(status, icons["running"])
    console.print(f"  {icon} [bold]\\[{step_num}/{total}][/] {description}")


def print_step_detail(detail: str, indent: int = 2) -> None:
    """Print a sub-detail under a step."""
    pad = "  " * indent
    console.print(f"{pad}[dim]├──[/] {detail}")


def print_step_detail_last(detail: str, indent: int = 2) -> None:
    """Print the last sub-detail under a step."""
    pad = "  " * indent
    console.print(f"{pad}[dim]└──[/] {detail}")


def print_report(report: dict) -> None:
    """Print the final results report."""
    coverage_before = report.get("coverage_before", 0)
    coverage_after = report.get("coverage_after", 0)
    delta = coverage_after - coverage_before

    # Results panel
    results = Table.grid(padding=(0, 2))
    results.add_column(justify="right", style="dim")
    results.add_column()

    results.add_row(
        "Coverage:",
        f"[bold]{coverage_before:.0%}[/] → [bold green]{coverage_after:.0%}[/] "
        f"([green]+{delta:.1%}[/])",
    )
    results.add_row(
        "Tests generated:",
        f"[bold]{report.get('tests_generated', 0)}[/] "
        f"(in {len(report.get('test_files_created', []))} files)",
    )
    results.add_row(
        "Iterations:",
        f"{report.get('iterations_used', 1)}/{3}",
    )

    passed = report.get("tests_passed", 0)
    failed = report.get("tests_failed", 0)
    if failed > 0:
        results.add_row(
            "Results:",
            f"[green]{passed} passed[/], [red]{failed} failed[/]",
        )
    else:
        results.add_row(
            "Results:",
            f"[green]{passed} passed[/], 0 failed ✓",
        )

    console.print()
    console.print(Panel(results, title="[bold]Results[/]", border_style="green"))

    # Per-file coverage table
    comparisons = report.get("coverage_comparisons", [])
    if comparisons:
        table = Table(title="Coverage Improvements", show_header=True, border_style="dim")
        table.add_column("File", style="cyan", no_wrap=True, max_width=50)
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Delta", justify="right")

        for comp in comparisons:
            before = comp.get("before_line_rate", 0)
            after = comp.get("after_line_rate", 0)
            d = after - before
            delta_str = f"[green]+{d:.1%}[/]" if d > 0 else f"{d:.1%}"

            # Shorten file path for display
            path = comp["file_path"]
            if "/" in path:
                path = "..." + path[path.rindex("/"):]

            table.add_row(path, f"{before:.0%}", f"{after:.0%}", delta_str)

        console.print(table)

    # Generated test files
    test_files = report.get("test_files_created", [])
    if test_files:
        tree = Tree("[bold]Generated Test Files[/]")
        for f in test_files:
            tree.add(f"[cyan]{f}[/]")
        console.print(tree)

    # Suggestions
    suggestions = report.get("suggestions", [])
    if suggestions:
        console.print()
        console.print("[yellow]⚠ Suggestions:[/]")
        for s in suggestions:
            console.print(f"  [dim]•[/] {s}")

    # Mutation testing report (if mutation mode)
    mutation = report.get("mutation")
    if mutation:
        _print_mutation_report(mutation)

    console.print()
    console.print(
        f"[dim]Report generated using {report.get('tool_calls', 0)} tool calls.[/]"
    )


def _print_mutation_report(mutation: dict) -> None:
    """Print the mutation testing section of the report."""
    score = mutation.get("mutation_score", 0.0)
    score_color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"

    console.print()

    # Mutation score summary
    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="dim")
    summary.add_column()

    summary.add_row(
        "Mutation score:",
        f"[bold {score_color}]{score:.0%}[/]"
        f" ({mutation.get('killed_by_existing', 0) + mutation.get('killed_by_new', 0)}"
        f"/{mutation.get('mutants_tested', 0)} mutants killed)",
    )
    summary.add_row(
        "Killed by existing:",
        f"[green]{mutation.get('killed_by_existing', 0)}[/]",
    )
    summary.add_row(
        "Killed by new tests:",
        f"[green]{mutation.get('killed_by_new', 0)}[/]",
    )
    survived = mutation.get("survived", 0)
    summary.add_row(
        "Still surviving:",
        f"[red]{survived}[/]" if survived > 0 else "[green]0[/]",
    )
    summary.add_row(
        "Equivalent (filtered):",
        f"[dim]{mutation.get('equivalent_filtered', 0)}[/]",
    )

    console.print(Panel(summary, title="[bold]Mutation Testing Results[/]", border_style="blue"))

    # Surviving mutants detail
    surviving = mutation.get("surviving_mutant_details", [])
    if surviving:
        table = Table(
            title="[yellow]Surviving Mutants — Not Caught by Tests[/]",
            show_header=True,
            border_style="yellow",
        )
        table.add_column("ID", style="dim", width=6)
        table.add_column("Type", style="cyan", width=18)
        table.add_column("Description")

        for m in surviving:
            table.add_row(
                m.get("mutant_id", ""),
                m.get("mutation_type", ""),
                m.get("mutation_description", ""),
            )
        console.print(table)


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red bold]Error:[/] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green bold]✓[/] {message}")
