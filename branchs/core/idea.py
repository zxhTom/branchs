"""Read the active IntelliJ IDEA changelist for a Git repository."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import git

from branchs.core.commit import get_staged_paths


@dataclass
class IdeaSelection:
    name: str
    paths: list[str]
    visible_paths: list[str]


def _project_dir(repo: git.Repo) -> Path:
    root = Path(repo.working_tree_dir).resolve()
    for directory in (root, *root.parents):
        if (directory / ".idea" / "workspace.xml").is_file():
            return directory
    children = [path.parent.parent for path in root.glob("*/.idea/workspace.xml")]
    if len(children) == 1:
        return children[0]
    if len(children) > 1:
        raise ValueError("Multiple IDEA projects found inside this repository; open the matching repository or use Add mode")
    raise ValueError("IDEA project not found: open this repository in IntelliJ IDEA or use Add mode")


def _relative_path(value: str, project: Path, repo_root: Path) -> Optional[str]:
    value = value.replace("\\", "/")
    prefix = "$PROJECT_DIR$"
    if value == prefix:
        return None
    if value.startswith(prefix + "/"):
        path = project / value[len(prefix) + 1:]
    else:
        path = Path(value)
        if not path.is_absolute():
            return None
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return None


def get_active_changelist(repo: git.Repo) -> IdeaSelection:
    project = _project_dir(repo)
    workspace = project / ".idea" / "workspace.xml"
    try:
        root = ElementTree.parse(workspace).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"Cannot read IDEA changelists from {workspace}: {exc}") from exc
    manager = root.find(".//component[@name='ChangeListManager']")
    if manager is None:
        raise ValueError("IDEA Changes data is missing from workspace.xml")
    lists = manager.findall("list")
    active = next((item for item in lists if item.get("default") == "true"), None)
    if active is None:
        raise ValueError("IDEA has no active changelist in workspace.xml")

    repo_root = Path(repo.working_tree_dir).resolve()

    def paths_for(item):
        paths = set()
        for change in item.findall("change"):
            for attr in ("beforePath", "afterPath"):
                value = change.get(attr)
                if value:
                    relative = _relative_path(value, project, repo_root)
                    if relative:
                        paths.add(relative)
        return paths

    selected = paths_for(active)
    other_paths = set().union(*(paths_for(item) for item in lists if item is not active))
    overlap = selected & other_paths
    if overlap:
        raise ValueError(
            "IDEA splits these files across changelists; commit them in IDEA to avoid including other hunks: "
            + ", ".join(sorted(overlap))
        )

    staged = set(get_staged_paths(repo))
    unstaged = set(filter(None, repo.git.diff("--name-only", "--no-renames", "-z").split("\0")))
    # Changes may contain modified files that are not staged. Show them in the
    # GUI but keep the commit selection limited to the existing Git index.
    # Unversioned Files do not appear in either Git diff.
    changed = staged | unstaged
    key = (lambda path: path.casefold()) if os.name == "nt" else (lambda path: path)
    matching = {key(path): path for path in changed}
    visible = sorted({matching[key(path)] for path in selected if key(path) in matching})
    staged_keys = {key(path) for path in staged}
    ready = [path for path in visible if key(path) in staged_keys]
    return IdeaSelection(active.get("name", "Changes"), ready, visible)


def commit_active_changelist(repo: git.Repo, message: Optional[str] = None, paths: Optional[list[str]] = None) -> tuple:
    selection = get_active_changelist(repo) if paths is None else None
    selected_paths = selection.paths if selection else paths
    if not selected_paths:
        return False, "No staged files in the active IDEA changelist; add files in IDEA first"
    outside = sorted(set(get_staged_paths(repo)) - set(selected_paths))
    if outside:
        return False, "Staged files outside the active IDEA changelist; unstage them first: " + ", ".join(outside)
    commit_message = message or "update IDEA changes"
    try:
        # No paths or -a: git commit records exactly the existing index.
        repo.git.commit("-m", commit_message)
        return True, commit_message
    except git.GitCommandError as exc:
        return False, str(exc)
