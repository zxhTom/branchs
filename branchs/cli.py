import sys
from typing import Optional

import click
import git
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.tree import Tree

from branchs.core.branch import (
    merge_branch,
    merge_to_multiple,
    merge_default_to_target,
    rebase_branch,
    get_sibling_branches,
    get_diff_between_branches,
    get_diff_summary,
    get_downstream_branches,
    get_upstream_branch,
    get_branch_fork_point,
    MergeResult,
    RebaseResult,
)
from branchs.core.commit import (
    commit_changes,
    get_commit_history,
    revert_commit,
    cherry_pick_commit,
    merge_file_from_source,
    generate_commit_message,
    CherryPickResult,
)
from branchs.core.config import (
    BranchType,
    load_config,
    set_branch_config,
    remove_branch_config,
    set_default_branch,
    set_remote_config,
    set_merge_mode,
    get_sibling_branches as config_get_siblings,
)
from branchs.core.git import (
    get_repo,
    get_current_branch,
    list_branches,
    list_remotes,
    get_remotes_info,
    has_uncommitted_changes,
    fetch_all,
    rebase_abort,
    rebase_continue,
    rebase_skip,
    is_rebasing,
)
from branchs.core.remote import sync_remotes

console = Console()


def get_repo_or_exit() -> Optional[git.Repo]:
    repo = get_repo()
    if not repo:
        console.print("[red]Not a git repository.[/red]")
        sys.exit(1)
    return repo


def print_result(success: bool, message: str) -> None:
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")


@click.group()
@click.version_option(version="0.1.0")
def main():
    """branchs - Multi-branch management tool"""


# ── branch commands ──────────────────────────────────────────────


@main.group()
def branch():
    """Branch management commands"""


@branch.command("list")
@click.option("--remote/--local", default=False, help="List remote branches")
def branch_list(remote: bool):
    """List all branches"""
    repo = get_repo_or_exit()
    branches = list_branches(repo, remote=remote)
    config = load_config()
    current = get_current_branch(repo)

    table = Table(title="Branches")
    table.add_column("Branch", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Upstream", style="green")
    table.add_column("Current", style="yellow")

    for name in branches:
        bc = config.branches.get(name)
        btype = bc.branch_type.value if bc else "-"
        upstream = bc.upstream if bc and bc.upstream else "-"
        mark = "●" if name == current else ""
        table.add_row(name, btype, upstream, mark)

    console.print(table)


@branch.command("set-type")
@click.argument("branch_name")
@click.argument("type_name")
@click.option("--upstream", "-u", help="Upstream branch name")
@click.option("--description", "-d", default="", help="Branch description")
def branch_set_type(branch_name: str, type_name: str, upstream: Optional[str], description: str):
    """Set branch type and upstream relationship"""
    try:
        btype = BranchType(type_name)
    except ValueError:
        console.print(f"[red]Invalid branch type. Valid types: {[t.value for t in BranchType]}[/red]")
        return

    set_branch_config(branch_name, btype, upstream, description)
    console.print(f"[green]✓[/green] Branch '{branch_name}' configured: type={type_name}, upstream={upstream}")


@branch.command("remove")
@click.argument("branch_name")
def branch_remove(branch_name: str):
    """Remove branch configuration"""
    remove_branch_config(branch_name)
    console.print(f"[green]✓[/green] Removed configuration for '{branch_name}'")


@branch.command("set-default")
@click.argument("branch_name")
def branch_set_default(branch_name: str):
    """Set the default source branch for merges"""
    set_default_branch(branch_name)
    console.print(f"[green]✓[/green] Default branch set to '{branch_name}'")


@branch.command("siblings")
@click.argument("branch_name", required=False)
def branch_siblings(branch_name: Optional[str]):
    """List sibling branches (branches from same fork point)"""
    repo = get_repo_or_exit()
    name = branch_name or get_current_branch(repo)
    siblings = get_sibling_branches(name, repo)

    if not siblings:
        console.print(f"[yellow]No sibling branches found for '{name}'[/yellow]")
        return

    fork = get_branch_fork_point(name, repo)
    console.print(f"[blue]Sibling branches of '{name}' (fork: {fork[:8] if fork else 'N/A'}):[/blue]")
    for s in siblings:
        console.print(f"  [cyan]{s}[/cyan]")


@branch.command("diff")
@click.argument("branch_a")
@click.argument("branch_b")
@click.option("--summary/--full", default=True, help="Show summary or full diff")
def branch_diff(branch_a: str, branch_b: str, summary: bool):
    """Show differences between two branches"""
    repo = get_repo_or_exit()
    if summary:
        output = get_diff_summary(repo, branch_a, branch_b)
        console.print(f"[blue]Diff summary: {branch_a}...{branch_b}[/blue]")
        console.print(output or "No differences")
    else:
        output = get_diff_between_branches(repo, branch_a, branch_b)
        if output:
            console.print(Syntax(output, "diff"))
        else:
            console.print("No differences")


@branch.command("rebase")
@click.option("--upstream", "-u", "-t", "--target", required=True, help="Upstream branch to rebase onto")
@click.option("--branch", "-b", "-s", "--source", default=None, help="Branch to rebase (defaults to current branch)")
@click.option("--mode", type=click.Choice(["abort", "keep"]), help="Conflict resolution mode")
@click.option("--onto", help="Rebase onto a specific base")
def branch_rebase(upstream: str, branch: Optional[str], mode: Optional[str], onto: Optional[str]):
    """Rebase current branch (or specified branch) onto upstream branch"""
    repo = get_repo_or_exit()
    report = rebase_branch(repo, upstream=upstream, branch=branch, mode=mode, onto=onto)
    _print_rebase_report(report)


# ── merge commands ───────────────────────────────────────────────


@main.group()
def merge():
    """Merge operations"""


@merge.command("do")
@click.option("--source", "-s", help="Source branch")
@click.option("--target", "-t", required=True, help="Target branch")
@click.option("--mode", type=click.Choice(["abort", "keep"]), help="Conflict resolution mode")
@click.option("--no-ff", is_flag=True, help="Disable fast-forward merge")
def merge_do(source: Optional[str], target: str, mode: Optional[str], no_ff: bool):
    """Merge source branch into target branch"""
    repo = get_repo_or_exit()

    if source is None:
        config = load_config()
        if config.default_branch:
            source = config.default_branch
        else:
            console.print("[red]No source branch specified and no default branch configured[/red]")
            return

    report = merge_branch(repo, source, target, mode=mode, no_ff=no_ff)
    _print_merge_report(report)


@merge.command("multi")
@click.option("--source", "-s", required=True, help="Source branch")
@click.option("--targets", "-t", multiple=True, required=True, help="Target branches (can specify multiple)")
@click.option("--mode", type=click.Choice(["abort", "keep"]), help="Conflict resolution mode")
def merge_multi(source: str, targets: tuple, mode: Optional[str]):
    """Merge source branch into multiple target branches"""
    repo = get_repo_or_exit()
    reports = merge_to_multiple(repo, source, list(targets), mode=mode)

    table = Table(title=f"Merge '{source}' to multiple targets")
    table.add_column("Target", style="cyan")
    table.add_column("Result", style="yellow")
    table.add_column("Message")

    for report in reports:
        icon = "✓" if report.result == MergeResult.SUCCESS else "✗"
        table.add_row(report.target, icon, report.message)

    console.print(table)


@merge.command("default")
@click.option("--target", "-t", required=True, help="Target branch")
@click.option("--mode", type=click.Choice(["abort", "keep"]), help="Conflict resolution mode")
def merge_default(target: str, mode: Optional[str]):
    """Merge default branch into target branch"""
    repo = get_repo_or_exit()
    report = merge_default_to_target(repo, target, mode=mode)
    if report:
        _print_merge_report(report)
    else:
        console.print("[red]No default branch configured. Use 'branch set-default' first.[/red]")


# ── rebase commands ──────────────────────────────────────────────


@main.group()
def rebase():
    """Rebase operations"""


@rebase.command("do")
@click.option("--upstream", "-u", "-t", "--target", required=True, help="Upstream branch to rebase onto (e.g. b branch)")
@click.option("--branch", "-b", "-s", "--source", default=None, help="Branch to rebase (defaults to current branch, e.g. a branch)")
@click.option("--mode", type=click.Choice(["abort", "keep"]), help="Conflict resolution mode")
@click.option("--onto", help="Rebase onto a specific base commit/branch")
def rebase_do(upstream: str, branch: Optional[str], mode: Optional[str], onto: Optional[str]):
    """Rebase current branch (or specified branch) onto upstream branch"""
    repo = get_repo_or_exit()
    report = rebase_branch(repo, upstream=upstream, branch=branch, mode=mode, onto=onto)
    _print_rebase_report(report)


@rebase.command("abort")
def rebase_abort_cmd():
    """Abort an in-progress rebase"""
    repo = get_repo_or_exit()
    success, msg = rebase_abort(repo)
    print_result(success, msg)


@rebase.command("continue")
def rebase_continue_cmd():
    """Continue an in-progress rebase after resolving conflicts"""
    repo = get_repo_or_exit()
    success, msg = rebase_continue(repo)
    print_result(success, msg)


@rebase.command("skip")
def rebase_skip_cmd():
    """Skip current commit during an in-progress rebase"""
    repo = get_repo_or_exit()
    success, msg = rebase_skip(repo)
    print_result(success, msg)


# ── commit commands ──────────────────────────────────────────────


@main.group()
def commit():
    """Commit management commands"""


@commit.command("auto")
@click.option("--message", "-m", help="Custom commit message")
@click.option("--file", "-f", multiple=True, help="Stage specific files")
def commit_auto(message: Optional[str], file: tuple):
    """Auto-generate commit from current changes"""
    repo = get_repo_or_exit()

    if not has_uncommitted_changes(repo):
        console.print("[yellow]No changes to commit[/yellow]")
        return

    files_list = list(file) if file else None
    success, msg = commit_changes(repo, message=message, files=files_list)

    if success:
        console.print(f"[green]✓[/green] Committed: {msg}")
    else:
        console.print(f"[red]✗[/red] {msg}")


@commit.command("suggest")
def commit_suggest():
    """Show suggested commit message based on current changes"""
    repo = get_repo_or_exit()
    msg = generate_commit_message(repo)
    if msg:
        console.print(f"[blue]Suggested message:[/blue] [cyan]{msg}[/cyan]")
    else:
        console.print("[yellow]No changes detected[/yellow]")


@commit.command("log")
@click.option("--branch", "-b", help="Branch to show history of")
@click.option("--author", "-a", help="Filter by author")
@click.option("--since", help="Filter by date (e.g. '2024-01-01')")
@click.option("--grep", "-g", help="Filter by commit message")
@click.option("--count", "-n", default=20, help="Number of commits to show")
def commit_log(branch: Optional[str], author: Optional[str], since: Optional[str], grep: Optional[str], count: int):
    """View commit history"""
    repo = get_repo_or_exit()
    commits = get_commit_history(
        repo, branch=branch, max_count=count, author_filter=author, since=since, message_filter=grep
    )

    if not commits:
        console.print("[yellow]No commits found[/yellow]")
        return

    table = Table(title=f"Commit History ({len(commits)} commits)")
    table.add_column("Hash", style="cyan", width=10)
    table.add_column("Author", style="magenta", width=20)
    table.add_column("Date", style="green", width=12)
    table.add_column("Message")

    for c in commits:
        table.add_row(c.hash[:8], c.author[:20], c.date.strftime("%Y-%m-%d"), c.message[:60])

    console.print(table)


@commit.command("revert")
@click.argument("commit_hash")
@click.option("--no-edit/--edit", default=True)
def commit_revert(commit_hash: str, no_edit: bool):
    """Revert a specific commit"""
    repo = get_repo_or_exit()
    success, msg = revert_commit(repo, commit_hash, no_edit=no_edit)
    print_result(success, msg)


@commit.command("cherry-pick")
@click.argument("commit_hash")
@click.option("--target", "-t", required=True, help="Target branch")
@click.option("--mode", type=click.Choice(["abort", "keep"]), default="abort")
def commit_cherry_pick(commit_hash: str, target: str, mode: str):
    """Cherry-pick a commit to another branch"""
    repo = get_repo_or_exit()
    report = cherry_pick_commit(repo, commit_hash, target, mode=mode)

    if report.result == CherryPickResult.SUCCESS:
        console.print(f"[green]✓[/green] {report.message}")
    elif report.result == CherryPickResult.ABORTED:
        console.print(f"[yellow]⊘[/yellow] {report.message}")
    elif report.result == CherryPickResult.CONFLICT:
        console.print(f"[yellow]![/yellow] {report.message}")
    else:
        console.print(f"[red]✗[/red] {report.message}")

    if report.conflict_files:
        console.print(f"[red]Conflict files:[/red] {', '.join(report.conflict_files)}")

    if report.related_files_count > 0:
        console.print(f"[blue]Related files: {report.related_files_count}[/blue]")
    if report.suggestion:
        console.print(f"[yellow]Suggestion: {report.suggestion}[/yellow]")
    if not report.worth_doing:
        console.print(f"[red]Warning: Cherry-pick may not be worth it![/red]")


# ── file commands ────────────────────────────────────────────────


@main.group()
def file():
    """File-level merge operations"""


@file.command("merge")
@click.argument("file_path")
@click.option("--source", "-s", required=True, help="Source branch")
@click.option("--target", "-t", required=True, help="Target branch")
@click.option("--mode", type=click.Choice(["abort", "keep"]), default="abort")
def file_merge(file_path: str, source: str, target: str, mode: str):
    """Merge a specific file from source to target branch"""
    repo = get_repo_or_exit()
    report = merge_file_from_source(repo, file_path, source, target, mode=mode)
    _print_merge_report(report)


# ── remote commands ──────────────────────────────────────────────


@main.group()
def remote():
    """Remote management commands"""


@remote.command("list")
def remote_list():
    """List all detected remotes in the repository"""
    repo = get_repo_or_exit()
    remotes = get_remotes_info(repo)
    if not remotes:
        console.print("[yellow]No remotes found in repository[/yellow]")
        return

    table = Table(title="Git Remotes")
    table.add_column("Remote", style="cyan")
    table.add_column("URL", style="green")

    for r in remotes:
        table.add_row(r["name"], r["url"])

    console.print(table)


@remote.command("set")
@click.option("--primary", "-p", required=True, help="Primary remote name")
@click.option("--secondary", "-s", required=True, help="Secondary remote name")
def remote_set(primary: str, secondary: str):
    """Configure primary and secondary remotes"""
    set_remote_config(primary, secondary)
    console.print(f"[green]✓[/green] Remote config: primary={primary}, secondary={secondary}")


@remote.command("sync")
@click.option("--primary", "-p", help="Primary remote (overrides config)")
@click.option("--secondary", "-s", help="Secondary remote (overrides config)")
def remote_sync(primary: Optional[str], secondary: Optional[str]):
    """Sync branches from primary to secondary remote"""
    repo = get_repo_or_exit()
    report = sync_remotes(repo, primary, secondary)
    console.print(report.summary())


# ── config commands ──────────────────────────────────────────────


@main.group()
def config():
    """Configuration management"""


@config.command("show")
def config_show():
    """Show current configuration"""
    config = load_config()
    console.print_json(data=config.to_dict())


@config.command("set-mode")
@click.argument("mode", type=click.Choice(["abort", "keep"]))
def config_set_mode(mode: str):
    """Set default merge conflict resolution mode"""
    set_merge_mode(mode)
    console.print(f"[green]✓[/green] Default merge mode set to '{mode}'")


# ── helpers ──────────────────────────────────────────────────────


def _print_merge_report(report) -> None:
    if report.result == MergeResult.SUCCESS:
        console.print(f"[green]✓[/green] {report.message}")
    elif report.result == MergeResult.ABORTED:
        console.print(f"[yellow]⊘[/yellow] {report.message}")
        if report.conflict_files:
            console.print(f"[red]Conflict files:[/red] {', '.join(report.conflict_files)}")
    elif report.result == MergeResult.KEPT:
        console.print(f"[yellow]![/yellow] {report.message}")
        if report.conflict_files:
            console.print(f"[red]Conflict files:[/red] {', '.join(report.conflict_files)}")
    else:
        console.print(f"[red]✗[/red] {report.message}")


def _print_rebase_report(report) -> None:
    if report.result == RebaseResult.SUCCESS:
        console.print(f"[green]✓[/green] {report.message}")
    elif report.result == RebaseResult.ABORTED:
        console.print(f"[yellow]⊘[/yellow] {report.message}")
        if report.conflict_files:
            console.print(f"[red]Conflict files:[/red] {', '.join(report.conflict_files)}")
    elif report.result == RebaseResult.KEPT:
        console.print(f"[yellow]![/yellow] {report.message}")
        if report.conflict_files:
            console.print(f"[red]Conflict files:[/red] {', '.join(report.conflict_files)}")
    else:
        console.print(f"[red]✗[/red] {report.message}")


if __name__ == "__main__":
    main()

