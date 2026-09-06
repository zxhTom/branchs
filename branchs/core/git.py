import os
import subprocess
from typing import Optional

import git


def _run_git(args: list, repo_path: str = ".") -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def get_repo(path: str = ".") -> Optional[git.Repo]:
    try:
        return git.Repo(path, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return None


def get_current_branch(repo: git.Repo) -> str:
    try:
        return repo.active_branch.name
    except TypeError:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


def checkout_branch(repo: git.Repo, name: str, create: bool = False) -> bool:
    try:
        if create and name not in [b.name for b in repo.branches]:
            repo.git.checkout("-b", name)
        else:
            repo.git.checkout(name)
        return True
    except git.GitCommandError:
        return False


def create_branch(repo: git.Repo, name: str, base: Optional[str] = None) -> bool:
    try:
        if base:
            repo.git.checkout("-b", name, base)
        else:
            repo.git.checkout("-b", name)
        return True
    except git.GitCommandError:
        return False


def delete_branch(repo: git.Repo, name: str, force: bool = False) -> bool:
    try:
        if force:
            repo.git.branch("-D", name)
        else:
            repo.git.branch("-d", name)
        return True
    except git.GitCommandError:
        return False


def list_branches(repo: git.Repo, remote: bool = False) -> list:
    if remote:
        return [ref.name.replace("origin/", "") for ref in repo.remote().refs]
    return [b.name for b in repo.branches]


def get_branch_fork_point(branch_name: str, repo: git.Repo) -> Optional[str]:
    try:
        return repo.git.merge_base(branch_name, "HEAD").strip() or None
    except git.GitCommandError:
        try:
            main_branch = "main" if "main" in [b.name for b in repo.branches] else "master"
            return repo.git.merge_base(branch_name, main_branch).strip() or None
        except git.GitCommandError:
            return None


def has_uncommitted_changes(repo: git.Repo) -> bool:
    return repo.is_dirty(untracked_files=True)


def stash_changes(repo: git.Repo) -> bool:
    if has_uncommitted_changes(repo):
        try:
            repo.git.stash()
            return True
        except git.GitCommandError:
            return False
    return True


def pop_stash(repo: git.Repo) -> bool:
    try:
        repo.git.stash("pop")
        return True
    except git.GitCommandError:
        return False


def get_commit_hash(repo: git.Repo, ref: str = "HEAD") -> str:
    return repo.git.rev_parse(ref).strip()


def fetch_all(repo: git.Repo) -> bool:
    try:
        for remote in repo.remotes:
            remote.fetch()
        return True
    except git.GitCommandError:
        return False


def is_rebasing(repo: git.Repo) -> bool:
    git_dir = repo.git_dir
    return os.path.exists(os.path.join(git_dir, "rebase-merge")) or os.path.exists(
        os.path.join(git_dir, "rebase-apply")
    )


def rebase_abort(repo: git.Repo) -> tuple[bool, str]:
    try:
        msg = repo.git.rebase("--abort")
        return True, msg or "Rebase aborted successfully"
    except git.GitCommandError as e:
        return False, str(e)


def rebase_continue(repo: git.Repo) -> tuple[bool, str]:
    try:
        msg = repo.git.rebase("--continue")
        return True, msg or "Rebase continued successfully"
    except git.GitCommandError as e:
        return False, str(e)


def rebase_skip(repo: git.Repo) -> tuple[bool, str]:
    try:
        msg = repo.git.rebase("--skip")
        return True, msg or "Commit skipped successfully"
    except git.GitCommandError as e:
        return False, str(e)


def list_remotes(repo: git.Repo) -> list[str]:
    """Return a list of remote names for the repository."""
    try:
        return [r.name for r in repo.remotes]
    except Exception:
        return []


def get_remotes_info(repo: git.Repo) -> list[dict]:
    """Return detailed information for all remotes (name, url, fetch/push urls)."""
    remotes_info = []
    try:
        for r in repo.remotes:
            urls = list(r.urls)
            remotes_info.append(
                {
                    "name": r.name,
                    "url": urls[0] if urls else "",
                    "all_urls": urls,
                }
            )
    except Exception:
        pass
    return remotes_info


