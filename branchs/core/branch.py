from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import git

from branchs.core.config import BranchType, get_branch_config, load_config
from branchs.core.git import (
    checkout_branch,
    create_branch,
    get_current_branch,
    get_repo,
    stash_changes,
    pop_stash,
    has_uncommitted_changes,
)


class MergeResult(Enum):
    SUCCESS = "success"
    CONFLICT = "conflict"
    ABORTED = "aborted"
    KEPT = "kept"
    FAILED = "failed"


@dataclass
class MergeReport:
    result: MergeResult
    source: str
    target: str
    message: str
    conflict_files: list = field(default_factory=list)


def merge_branch(
    repo: git.Repo,
    source: str,
    target: str,
    mode: Optional[str] = None,
    no_ff: bool = False,
) -> MergeReport:
    if mode is None:
        config = load_config()
        mode = config.default_merge_mode

    original_branch = get_current_branch(repo)

    try:
        if not checkout_branch(repo, target):
            return MergeReport(
                result=MergeResult.FAILED,
                source=source,
                target=target,
                message=f"Failed to checkout target branch '{target}'",
            )

        merge_args = [source]
        if no_ff:
            merge_args.insert(0, "--no-ff")

        try:
            repo.git.merge(*merge_args)
            checkout_branch(repo, original_branch)
            return MergeReport(
                result=MergeResult.SUCCESS,
                source=source,
                target=target,
                message=f"Successfully merged '{source}' into '{target}'",
            )
        except git.GitCommandError:
            conflict_files = _get_conflict_files(repo)

            if mode == "abort":
                repo.git.merge("--abort")
                checkout_branch(repo, original_branch)
                return MergeReport(
                    result=MergeResult.ABORTED,
                    source=source,
                    target=target,
                    message=f"Merge aborted due to conflicts in {len(conflict_files)} file(s)",
                    conflict_files=conflict_files,
                )
            else:
                checkout_branch(repo, original_branch)
                return MergeReport(
                    result=MergeResult.KEPT,
                    source=source,
                    target=target,
                    message=f"Merge conflicts detected in {len(conflict_files)} file(s). Status preserved on '{target}'.",
                    conflict_files=conflict_files,
                )
    finally:
        try:
            checkout_branch(repo, original_branch)
        except git.GitCommandError:
            pass


def merge_to_multiple(
    repo: git.Repo,
    source: str,
    targets: list,
    mode: Optional[str] = None,
) -> list:
    reports = []
    for target in targets:
        report = merge_branch(repo, source, target, mode=mode)
        reports.append(report)
    return reports


def merge_default_to_target(
    repo: git.Repo,
    target: str,
    mode: Optional[str] = None,
) -> Optional[MergeReport]:
    config = load_config()
    if not config.default_branch:
        return None
    return merge_branch(repo, config.default_branch, target, mode=mode)


def get_branch_fork_point(branch_name: str, repo: git.Repo) -> Optional[str]:
    from branchs.core.git import get_branch_fork_point as gfp

    return gfp(branch_name, repo)


def get_sibling_branches(branch_name: str, repo: git.Repo) -> list:
    fork_point = get_branch_fork_point(branch_name, repo)
    if not fork_point:
        return []
    siblings = []
    for b in repo.branches:
        if b.name == branch_name:
            continue
        bfp = get_branch_fork_point(b.name, repo)
        if bfp == fork_point:
            siblings.append(b.name)
    return siblings


def get_diff_between_branches(
    repo: git.Repo,
    branch_a: str,
    branch_b: str,
) -> str:
    try:
        return repo.git.diff(f"{branch_a}...{branch_b}")
    except git.GitCommandError:
        return ""


def get_diff_summary(
    repo: git.Repo,
    branch_a: str,
    branch_b: str,
) -> str:
    try:
        return repo.git.diff("--stat", f"{branch_a}...{branch_b}")
    except git.GitCommandError:
        return ""


def get_downstream_branches(branch_name: str, repo: git.Repo) -> list:
    config = load_config()
    downstream = []
    for name, bc in config.branches.items():
        if bc.upstream == branch_name and name in [b.name for b in repo.branches]:
            downstream.append(name)
    return downstream


def get_upstream_branch(branch_name: str) -> Optional[str]:
    bc = get_branch_config(branch_name)
    if bc and bc.upstream:
        return bc.upstream
    return None


def get_branch_type_flow(target_type: BranchType) -> list:
    flow_map = {
        BranchType.FEATURE: [BranchType.PROJECT],
        BranchType.PROJECT: [BranchType.MAIN],
        BranchType.RELEASE: [BranchType.MAIN],
        BranchType.HOTFIX: [BranchType.MAIN, BranchType.PROJECT, BranchType.RELEASE],
        BranchType.MAIN: [],
    }
    return flow_map.get(target_type, [])


def _get_conflict_files(repo: git.Repo) -> list:
    try:
        output = repo.git.diff("--name-only", "--diff-filter=U")
        return [f for f in output.strip().split("\n") if f]
    except git.GitCommandError:
        return []
