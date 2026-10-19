"""Repository selection for the GUI."""

from pathlib import Path
from typing import Optional

import git

from branchs.core.config import load_config


def open_repository(path: str) -> git.Repo:
    folder = Path(path).expanduser()
    if not folder.is_dir():
        raise ValueError(f"Repository folder does not exist: {path}")
    try:
        repo = git.Repo(str(folder), search_parent_directories=True)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError) as exc:
        raise ValueError(f"Not a Git repository: {path}") from exc
    if repo.bare or not repo.working_tree_dir:
        raise ValueError(f"Bare repositories cannot be opened in the GUI: {path}")
    return repo


def startup_repository() -> Optional[git.Repo]:
    config = load_config()
    candidates = [config.last_repo, *config.recent_repos, str(Path.cwd())]
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        try:
            return open_repository(path)
        except (ValueError, OSError):
            continue
    return None
