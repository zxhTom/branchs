"""Read the active IntelliJ IDEA changelist for a Git repository."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import git


@dataclass
class IdeaSelection:
    name: str
    paths: list[str]


def _project_dir(repo: git.Repo) -> Path:
    root = Path(repo.working_tree_dir).resolve()
    for directory in (root, *root.parents):
        if (directory / ".idea" / "workspace.xml").is_file():
            return directory
    raise ValueError("IDEA project not found: open this repository in IntelliJ IDEA first")


def _relative_path(value: str, project: Path, repo_root: Path) -> Optional[str]:
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

    # IDEA's Unversioned Files are not part of a changelist. Require every
    # selected path to be known to Git so a rename cannot become a deletion.
    unversioned = [path for path in sorted(selected) if not repo.git.ls_files("--cached", "--", path)]
    if unversioned:
        raise ValueError("Add these IDEA files to Git first: " + ", ".join(unversioned))

    changed = [
        path for path in sorted(selected)
        if repo.git.status("--porcelain=v1", "--untracked-files=no", "--", path)
    ]
    return IdeaSelection(active.get("name", "Changes"), changed)


def commit_active_changelist(repo: git.Repo, message: Optional[str] = None, paths: Optional[list[str]] = None) -> tuple:
    selection = get_active_changelist(repo) if paths is None else None
    selected_paths = selection.paths if selection else paths
    if not selected_paths:
        return False, "No changed files in the active IDEA changelist"
    commit_message = message or "update IDEA changes"
    try:
        # --only ignores already staged files outside this path list.
        repo.git.commit("--only", "-m", commit_message, "--", *selected_paths)
        return True, commit_message
    except git.GitCommandError as exc:
        return False, str(exc)
