from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import git

from branchs.core.branch import MergeReport, MergeResult, _get_conflict_files
from branchs.core.git import checkout_branch, get_current_branch


class CherryPickResult(Enum):
    SUCCESS = "success"
    CONFLICT = "conflict"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass
class CommitInfo:
    hash: str
    author: str
    date: datetime
    message: str
    files_changed: list = field(default_factory=list)


@dataclass
class CherryPickReport:
    result: CherryPickResult
    commit: str
    target_branch: str
    message: str
    conflict_files: list = field(default_factory=list)
    related_files_count: int = 0
    worth_doing: bool = True
    suggestion: str = ""


def get_commit_history(
    repo: git.Repo,
    branch: Optional[str] = None,
    max_count: int = 50,
    author_filter: Optional[str] = None,
    since: Optional[str] = None,
    message_filter: Optional[str] = None,
) -> list:
    log_args = ["--format=%H|%an|%aI|%s", f"--max-count={max_count}"]
    if branch:
        log_args.append(branch)
    if author_filter:
        log_args.append(f"--author={author_filter}")
    if since:
        log_args.append(f"--since={since}")
    if message_filter:
        log_args.append(f"--grep={message_filter}")

    try:
        output = repo.git.log(*log_args)
        commits = []
        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            commits.append(
                CommitInfo(
                    hash=parts[0],
                    author=parts[1],
                    date=datetime.fromisoformat(parts[2]),
                    message=parts[3],
                )
            )
        return commits
    except git.GitCommandError:
        return []


def generate_commit_message(repo: git.Repo) -> str:
    try:
        status = repo.git.status("--short")
        if not status.strip():
            return ""


        files = []
        added = []
        modified = []
        deleted = []
        for line in status.strip().split("\n"):
            if not line:
                continue
            code = line[:2].strip()
            fname = line[3:]
            files.append(fname)
            if code == "M":
                modified.append(fname)
            elif code == "A" or code == "??":
                added.append(fname)
            elif code == "D":
                deleted.append(fname)

        parts = []
        if added:
            parts.append(f"add {', '.join(added)}")
        if modified:
            parts.append(f"update {', '.join(modified)}")
        if deleted:
            parts.append(f"remove {', '.join(deleted)}")

        return "; ".join(parts) if parts else "update files"
    except git.GitCommandError:
        return ""


def commit_changes(
    repo: git.Repo,
    message: Optional[str] = None,
    files: Optional[list] = None,
    all_changes: bool = True,
) -> tuple:
    if message is None:
        message = generate_commit_message(repo)
        if not message:
            return False, "No changes to commit"

    try:
        if files:
            repo.git.add(*files)
        elif all_changes:
            repo.git.add(".")

        repo.git.commit("-m", message)
        return True, message
    except git.GitCommandError as e:
        return False, str(e)


def revert_commit(
    repo: git.Repo,
    commit_hash: str,
    no_edit: bool = True,
) -> tuple:
    try:
        args = ["revert"]
        if no_edit:
            args.append("--no-edit")
        args.append(commit_hash)
        repo.git(*args)
        return True, f"Reverted commit {commit_hash}"
    except git.GitCommandError as e:
        return False, str(e)


def cherry_pick_commit(
    repo: git.Repo,
    commit_hash: str,
    target_branch: str,
    mode: str = "abort",
) -> CherryPickReport:
    original_branch = get_current_branch(repo)

    try:
        diff_stats = _get_commit_diff_stats(repo, commit_hash)
        related_count = len(diff_stats)
        worth, suggestion = _evaluate_cherry_pick_worth(related_count, diff_stats)

        if not checkout_branch(repo, target_branch):
            checkout_branch(repo, original_branch)
            return CherryPickReport(
                result=CherryPickResult.FAILED,
                commit=commit_hash,
                target_branch=target_branch,
                message=f"Failed to checkout target branch '{target_branch}'",
                related_files_count=related_count,
                worth_doing=worth,
                suggestion=suggestion,
            )

        try:
            repo.git.cherry_pick(commit_hash)
            checkout_branch(repo, original_branch)
            return CherryPickReport(
                result=CherryPickResult.SUCCESS,
                commit=commit_hash,
                target_branch=target_branch,
                message=f"Successfully cherry-picked {commit_hash} to '{target_branch}'",
                related_files_count=related_count,
                worth_doing=worth,
                suggestion=suggestion,
            )
        except git.GitCommandError:
            conflict_files = _get_conflict_files(repo)

            if mode == "abort":
                repo.git.cherry_pick("--abort")
                checkout_branch(repo, original_branch)
                return CherryPickReport(
                    result=CherryPickResult.ABORTED,
                    commit=commit_hash,
                    target_branch=target_branch,
                    message=f"Cherry-pick aborted due to conflicts in {len(conflict_files)} file(s)",
                    conflict_files=conflict_files,
                    related_files_count=related_count,
                    worth_doing=worth,
                    suggestion=suggestion,
                )
            else:
                checkout_branch(repo, original_branch)
                return CherryPickReport(
                    result=CherryPickResult.CONFLICT,
                    commit=commit_hash,
                    target_branch=target_branch,
                    message=f"Cherry-pick conflicts in {len(conflict_files)} file(s). Status preserved.",
                    conflict_files=conflict_files,
                    related_files_count=related_count,
                    worth_doing=worth,
                    suggestion=suggestion,
                )
    finally:
        try:
            checkout_branch(repo, original_branch)
        except git.GitCommandError:
            pass


def merge_file_from_source(
    repo: git.Repo,
    file_path: str,
    source: str,
    target: str,
    mode: str = "abort",
) -> MergeReport:
    original_branch = get_current_branch(repo)

    analysis = _analyze_file_merge(repo, file_path, source, target)
    if not analysis.get("worth_it", True):
        return MergeReport(
            result=MergeResult.FAILED,
            source=source,
            target=target,
            message=f"Merge not recommended: {analysis.get('reason', '')}",
        )

    try:
        if not checkout_branch(repo, target):
            return MergeReport(
                result=MergeResult.FAILED,
                source=source,
                target=target,
                message=f"Failed to checkout '{target}'",
            )

        try:
            repo.git.checkout(source, "--", file_path)
            conflict_files = _get_conflict_files(repo)
            if conflict_files:
                if mode == "abort":
                    repo.git.checkout("HEAD", "--", file_path)
                    checkout_branch(repo, original_branch)
                    return MergeReport(
                        result=MergeResult.ABORTED,
                        source=source,
                        target=target,
                        message=f"File merge aborted due to conflicts",
                        conflict_files=conflict_files,
                    )
                else:
                    checkout_branch(repo, original_branch)
                    return MergeReport(
                        result=MergeResult.KEPT,
                        source=source,
                        target=target,
                        message=f"File '{file_path}' has conflicts. Status preserved.",
                        conflict_files=conflict_files,
                    )

            checkout_branch(repo, original_branch)
            return MergeReport(
                result=MergeResult.SUCCESS,
                source=source,
                target=target,
                message=f"File '{file_path}' merged from '{source}' to '{target}'. "
                f"Additional related files: {len(analysis.get('related_files', []))}",
            )
        except git.GitCommandError as e:
            checkout_branch(repo, original_branch)
            return MergeReport(
                result=MergeResult.FAILED,
                source=source,
                target=target,
                message=str(e),
            )
    finally:
        try:
            checkout_branch(repo, original_branch)
        except git.GitCommandError:
            pass


def _get_commit_diff_stats(repo: git.Repo, commit_hash: str) -> list:
    try:
        output = repo.git.diff_tree("--no-commit-id", "--name-only", "-r", commit_hash)
        return [f for f in output.strip().split("\n") if f]
    except git.GitCommandError:
        return []


def _evaluate_cherry_pick_worth(file_count: int, files: list) -> tuple:
    if file_count == 0:
        return True, ""
    if file_count > 20:
        return False, f"Large change: {file_count} files affected. Consider alternative approach."
    if file_count > 10:
        return True, f"Moderate change: {file_count} files affected. Review dependencies carefully."
    return True, ""


def _analyze_file_merge(repo: git.Repo, file_path: str, source: str, target: str) -> dict:
    try:
        related = _get_related_files(repo, file_path, source, target)
        too_many = len(related) > 30
        return {
            "worth_it": not too_many,
            "reason": f"Too many related files ({len(related)})" if too_many else "",
            "related_files": related,
        }
    except Exception:
        return {"worth_it": True, "reason": "", "related_files": []}


def _get_related_files(repo: git.Repo, file_path: str, source: str, target: str) -> list:
    try:
        diff_output = repo.git.diff("--name-only", f"{target}...{source}")
        return [f for f in diff_output.strip().split("\n") if f and f != file_path]
    except git.GitCommandError:
        return []
