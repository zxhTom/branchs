"""Synchronize each branch from one remote to another without force pushing."""

from dataclasses import dataclass, field
from typing import Optional

import git

from branchs.core.config import load_config
from branchs.core.network import git_network


@dataclass
class SyncItem:
    branch: str
    status: str
    message: str


@dataclass
class SyncReport:
    primary: str = ""
    secondary: str = ""
    synced: list[SyncItem] = field(default_factory=list)
    failed: list[SyncItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.synced) + len(self.failed)

    def summary(self) -> str:
        lines = [f"SYNC REPORT  {self.primary} → {self.secondary}"]
        lines.append(f"Succeeded: {len(self.synced)}    Failed: {len(self.failed)}    Total: {self.total}")
        if self.synced:
            lines.append("\nSucceeded branches:")
            lines.extend(f"  [OK] {item.branch}: {item.message}" for item in self.synced)
        if self.failed:
            lines.append("\nFailed branches:")
            lines.extend(f"  [FAIL] {item.branch}: {item.message}" for item in self.failed)
        if not self.total:
            lines.append("\nNo branches found on the primary remote.")
        return "\n".join(lines)


def _remote_heads(repo: git.Repo, remote: str) -> dict[str, str]:
    heads = {}
    for line in repo.git.ls_remote("--heads", remote).splitlines():
        sha, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            heads[ref.removeprefix("refs/heads/")] = sha
    return heads


def _error_text(exc: git.GitCommandError) -> str:
    return " | ".join((exc.stderr or str(exc)).strip().splitlines())


def sync_remotes(repo: git.Repo, primary: Optional[str], secondary: Optional[str]) -> SyncReport:
    """Attempt every primary branch independently and report every outcome."""
    config = load_config().remote
    primary = primary or (config.primary if config else "origin")
    secondary = secondary or (config.secondary if config else "upstream")
    report = SyncReport(primary=primary, secondary=secondary)
    remote_names = {remote.name for remote in repo.remotes}
    if primary not in remote_names:
        report.failed.append(SyncItem("ALL", "failed", f"Primary remote '{primary}' not found"))
        return report
    if secondary not in remote_names:
        report.failed.append(SyncItem("ALL", "failed", f"Secondary remote '{secondary}' not found"))
        return report
    if primary == secondary:
        report.failed.append(SyncItem("ALL", "failed", "Primary and secondary must be different remotes"))
        return report

    with git_network(repo):
        try:
            primary_heads = _remote_heads(repo, primary)
        except git.GitCommandError as exc:
            report.failed.append(SyncItem("ALL", "failed", f"Cannot list primary branches: {_error_text(exc)}"))
            return report
        try:
            secondary_heads = _remote_heads(repo, secondary)
        except git.GitCommandError as exc:
            for branch in sorted(primary_heads):
                report.failed.append(SyncItem(branch, "failed", f"Cannot inspect secondary: {_error_text(exc)}"))
            return report

        for branch in sorted(primary_heads):
            try:
                # FETCH_HEAD is immediately resolved to an immutable commit ID,
                # so the next branch cannot change what this push sends.
                repo.git.fetch("--no-tags", primary, f"refs/heads/{branch}")
                source_sha = repo.git.rev_parse("FETCH_HEAD").strip()
                repo.git.push("--porcelain", secondary, f"{source_sha}:refs/heads/{branch}")
                if secondary_heads.get(branch) == source_sha:
                    message = "Already up to date"
                elif branch in secondary_heads:
                    message = "Updated by fast-forward"
                else:
                    message = "Created on secondary"
                report.synced.append(SyncItem(branch, "synced", message))
            except git.GitCommandError as exc:
                report.failed.append(SyncItem(branch, "failed", _error_text(exc)))

    return report
