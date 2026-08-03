from dataclasses import dataclass, field
from typing import Optional

import git

from branchs.core.branch import MergeReport, MergeResult, merge_branch
from branchs.core.config import load_config
from branchs.core.git import (
    checkout_branch,
    get_current_branch,
    get_repo,
    stash_changes,
    pop_stash,
    list_branches,
)


@dataclass
class SyncItem:
    branch: str
    status: str
    message: str


@dataclass
class SyncReport:
    synced: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.synced) + len(self.merged) + len(self.failed) + len(self.conflicts)

    def summary(self) -> str:
        lines = ["=" * 60, "SYNC REPORT", "=" * 60]

        if self.synced:
            lines.append(f"\nSuccessfully Synced ({len(self.synced)}):")
            for item in self.synced:
                lines.append(f"  [OK] {item.branch}: {item.message}")

        if self.merged:
            lines.append(f"\nMerged Successfully ({len(self.merged)}):")
            for item in self.merged:
                lines.append(f"  [MERGE] {item.branch}: {item.message}")

        if self.conflicts:
            lines.append(f"\nConflicts - Need Manual Resolution ({len(self.conflicts)}):")
            for item in self.conflicts:
                lines.append(f"  [CONFLICT] {item.branch}: {item.message}")

        if self.failed:
            lines.append(f"\nFailed ({len(self.failed)}):")
            for item in self.failed:
                lines.append(f"  [FAIL] {item.branch}: {item.message}")

        lines.append(f"\nTotal: {self.total} branches processed")
        return "\n".join(lines)


def sync_remotes(repo: git.Repo, primary: str, secondary: str) -> SyncReport:
    config = load_config()
    if not config.remote:
        primary = primary or "origin"
        secondary = secondary or "upstream"
    else:
        primary = primary or config.remote.primary
        secondary = secondary or config.remote.secondary

    report = SyncReport()

    if primary not in [r.name for r in repo.remotes]:
        report.failed.append(
            SyncItem(branch="ALL", status="failed", message=f"Primary remote '{primary}' not found")
        )
        return report
    if secondary not in [r.name for r in repo.remotes]:
        report.failed.append(
            SyncItem(branch="ALL", status="failed", message=f"Secondary remote '{secondary}' not found")
        )
        return report

    repo.remotes[primary].fetch()

    primary_branches = _get_remote_branches(repo, primary)
    secondary_branches = _get_remote_branches(repo, secondary)
    original_branch = get_current_branch(repo)

    for pbranch in primary_branches:
        full_primary_ref = f"{primary}/{pbranch}"
        if pbranch in secondary_branches:
            try:
                repo.git.checkout("-B", f"_sync_{pbranch}", full_primary_ref)
                repo.git.push(secondary, f"_sync_{pbranch}:{pbranch}")
                report.synced.append(
                    SyncItem(branch=pbranch, status="synced", message="Pushed to secondary")
                )
            except git.GitCommandError as e:
                report.conflicts.append(
                    SyncItem(
                        branch=pbranch,
                        status="conflict",
                        message=f"Merge conflict, preserved '{secondary}/{pbranch}'. Manual resolution needed. Error: {str(e)}",
                    )
                )
        else:
            try:
                repo.git.push(secondary, f"{full_primary_ref}:refs/heads/{pbranch}")
                report.synced.append(
                    SyncItem(branch=pbranch, status="synced", message="New branch synced")
                )
            except git.GitCommandError as e:
                report.failed.append(
                    SyncItem(branch=pbranch, status="failed", message=str(e))
                )

    try:
        checkout_branch(repo, original_branch)
    except git.GitCommandError:
        pass

    return report


def _get_remote_branches(repo: git.Repo, remote_name: str) -> list:
    branches = []
    for ref in repo.remotes[remote_name].refs:
        name = ref.name.replace(f"{remote_name}/", "")
        if name != "HEAD":
            branches.append(name)
    return branches
