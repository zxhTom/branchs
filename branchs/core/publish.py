"""Prepare a branch against its remote parent, then commit and publish it."""

from dataclasses import dataclass
from typing import Callable, Optional

import git

from branchs.core.commit import commit_changes, get_staged_paths
from branchs.core.config import get_branch_config
from branchs.core.git import get_current_branch, has_uncommitted_changes, is_rebasing
from branchs.core.network import git_network
from branchs.core.idea import commit_active_changelist, get_active_changelist


@dataclass
class PublishResult:
    success: bool
    message: str


@dataclass
class PublishSelection:
    description: str
    display: list[str]
    paths: list[str]


def _contains(repo: git.Repo, older: str) -> bool:
    return repo.git.merge_base(older, "HEAD").strip() == older


def get_publish_selection(repo: git.Repo, mode: str = "idea") -> PublishSelection:
    if mode == "all":
        paths = get_staged_paths(repo)
        display = repo.git.diff("--cached", "--name-status", "--no-renames").splitlines()
        return PublishSelection("all staged changes", display, paths)
    if mode != "idea":
        raise ValueError(f"Unknown publish mode: {mode}")
    changelist = get_active_changelist(repo)
    outside = sorted(set(get_staged_paths(repo)) - set(changelist.paths))
    if outside:
        raise ValueError("Staged files outside the active IDEA changelist; unstage them first: " + ", ".join(outside))
    display = []
    for path in changelist.paths:
        display.extend(repo.git.diff("--cached", "--name-status", "--no-renames", "--", path).splitlines())
    return PublishSelection(f"IDEA changelist '{changelist.name}'", display, changelist.paths)


def publish_branch(
    repo: git.Repo,
    message: Optional[str] = None,
    remote: str = "origin",
    mode: str = "idea",
    progress: Optional[Callable[[str], None]] = None,
) -> PublishResult:
    """Sync remote branch, rebase onto its configured parent, commit and push.

    A temporary stash keeps staged and untracked changes out of the rebases.
    On failure the stash is retained if it cannot be restored cleanly.
    """
    with git_network(repo):
        return _publish_branch(repo, message, remote, mode, progress)


def _publish_branch(repo: git.Repo, message: Optional[str], remote: str, mode: str,
                    progress: Optional[Callable[[str], None]] = None) -> PublishResult:
    def step(name: str) -> None:
        if progress:
            progress(name)

    step("检查仓库与暂存文件")
    branch = get_current_branch(repo)
    config = get_branch_config(branch)
    if not config or not config.upstream:
        return PublishResult(False, f"Set the parent of '{branch}' with branch set-type --upstream first")
    parent = config.upstream
    if branch == parent:
        return PublishResult(False, "A branch cannot be its own parent")
    if remote not in [r.name for r in repo.remotes]:
        return PublishResult(False, f"Remote '{remote}' does not exist")
    if is_rebasing(repo) or repo.git.ls_files("-u") or repo.git.rev_parse("-q", "--verify", "MERGE_HEAD", with_exceptions=False):
        return PublishResult(False, "Finish the current merge or rebase before publishing")

    try:
        selection = get_publish_selection(repo, mode)
    except ValueError as exc:
        return PublishResult(False, str(exc))
    if has_uncommitted_changes(repo) and not selection.paths:
        return PublishResult(False, "No staged files to commit; add files in Git or IDEA first")

    # Resolve and fetch both heads before changing the working tree. A missing
    # remote branch is fine for the first publication of a local branch.
    try:
        step("查询远端分支")
        heads = {}
        for line in repo.git.ls_remote("--heads", remote).splitlines():
            sha, ref = line.split("\t", 1)
            heads[ref] = sha
        parent_ref = f"refs/heads/{parent}"
        branch_ref = f"refs/heads/{branch}"
        if parent_ref not in heads:
            return PublishResult(False, f"Parent '{remote}/{parent}' does not exist")
        for name in (parent, branch):
            if f"refs/heads/{name}" in heads:
                step(f"获取 {remote}/{name}")
                repo.git.fetch(remote, f"+refs/heads/{name}:refs/remotes/{remote}/{name}")
    except git.GitCommandError as exc:
        return PublishResult(False, f"Fetch failed: {exc}")

    saved_changes = has_uncommitted_changes(repo)
    stash_oid = None
    if saved_changes:
        try:
            step("暂存工作区状态")
            before = repo.git.rev_parse("-q", "--verify", "refs/stash", with_exceptions=False)
            repo.git.stash("push", "-u", "-m", f"branchs publish {branch}")
            stash_oid = repo.git.rev_parse("refs/stash")
            if stash_oid == before or has_uncommitted_changes(repo):
                return PublishResult(False, "Could not safely save all working tree changes")
        except git.GitCommandError as exc:
            return PublishResult(False, f"Could not save working tree changes: {exc}")

    failure = None
    try:
        if branch_ref in heads and not _contains(repo, heads[branch_ref]):
            step(f"变基到 {remote}/{branch}")
            repo.git.rebase(f"refs/remotes/{remote}/{branch}")
        step(f"变基到 {remote}/{parent}")
        repo.git.rebase(f"refs/remotes/{remote}/{parent}")
    except git.GitCommandError as exc:
        failure = f"Rebase failed: {exc}"
        try:
            if is_rebasing(repo):
                repo.git.rebase("--abort")
        except git.GitCommandError as abort_exc:
            failure += f"; abort failed: {abort_exc}"

    if stash_oid:
        try:
            step("恢复工作区状态")
            repo.git.stash("apply", "--index", stash_oid)
            # The stash remains available until its changes are restored.
            if repo.git.rev_parse("refs/stash") == stash_oid:
                repo.git.stash("drop", "stash@{0}")
        except git.GitCommandError as exc:
            return PublishResult(False, f"{failure + '; ' if failure else ''}Restore changes manually from stash {stash_oid}: {exc}")
    if failure:
        return PublishResult(False, failure)

    if mode == "idea" and selection.paths:
        step("提交已暂存文件")
        success, result = commit_active_changelist(repo, message=message, paths=selection.paths)
        if not success:
            return PublishResult(False, f"Commit failed: {result}")
    elif mode == "all" and selection.paths:
        step("提交已暂存文件")
        success, result = commit_changes(repo, message=message)
        if not success:
            return PublishResult(False, f"Commit failed: {result}")

    try:
        step(f"推送到 {remote}/{branch}")
        # Use the exact remote value observed before the rebases as the lease.
        # A concurrent push is rejected even if a background fetch updates refs.
        if branch_ref in heads and not _contains(repo, heads[branch_ref]):
            repo.git.push(remote, f"--force-with-lease={branch_ref}:{heads[branch_ref]}", f"HEAD:{branch_ref}")
        else:
            repo.git.push(remote, f"HEAD:{branch_ref}")
    except git.GitCommandError as exc:
        return PublishResult(False, f"Commit is local, but push failed: {exc}")
    return PublishResult(True, f"Published '{branch}' after syncing '{remote}/{branch}' and rebasing onto '{remote}/{parent}'")
