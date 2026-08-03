import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

CONFIG_DIR = os.path.expanduser("~/.config/branchs")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


class BranchType(Enum):
    MAIN = "main"
    PROJECT = "project"
    FEATURE = "feature"
    RELEASE = "release"
    HOTFIX = "hotfix"


@dataclass
class BranchConfig:
    name: str
    branch_type: BranchType
    upstream: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.branch_type.value,
            "upstream": self.upstream,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BranchConfig":
        return cls(
            name=data["name"],
            branch_type=BranchType(data["type"]),
            upstream=data.get("upstream"),
            description=data.get("description", ""),
        )


@dataclass
class RemoteConfig:
    primary: str
    secondary: str

    def to_dict(self) -> dict:
        return {"primary": self.primary, "secondary": self.secondary}

    @classmethod
    def from_dict(cls, data: dict) -> "RemoteConfig":
        return cls(primary=data["primary"], secondary=data["secondary"])


@dataclass
class Config:
    default_branch: Optional[str] = None
    default_merge_mode: str = "abort"
    default_diff_tool: Optional[str] = None
    branches: dict = field(default_factory=dict)
    remote: Optional[RemoteConfig] = None

    def to_dict(self) -> dict:
        return {
            "default_branch": self.default_branch,
            "default_merge_mode": self.default_merge_mode,
            "default_diff_tool": self.default_diff_tool,
            "branches": {k: v.to_dict() for k, v in self.branches.items()},
            "remote": self.remote.to_dict() if self.remote else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        branches = {}
        for k, v in data.get("branches", {}).items():
            branches[k] = BranchConfig.from_dict(v)
        remote = RemoteConfig.from_dict(data["remote"]) if data.get("remote") else None
        return cls(
            default_branch=data.get("default_branch"),
            default_merge_mode=data.get("default_merge_mode", "abort"),
            default_diff_tool=data.get("default_diff_tool"),
            branches=branches,
            remote=remote,
        )


def load_config() -> Config:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return Config.from_dict(json.load(f))
    return Config()


def save_config(config: Config) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.to_dict(), f, indent=2)


def get_branch_config(name: str) -> Optional[BranchConfig]:
    config = load_config()
    return config.branches.get(name)


def set_branch_config(
    name: str,
    branch_type: BranchType,
    upstream: Optional[str] = None,
    description: str = "",
) -> None:
    config = load_config()
    config.branches[name] = BranchConfig(
        name=name, branch_type=branch_type, upstream=upstream, description=description
    )
    save_config(config)


def remove_branch_config(name: str) -> None:
    config = load_config()
    config.branches.pop(name, None)
    save_config(config)


def set_default_branch(name: str) -> None:
    config = load_config()
    config.default_branch = name
    save_config(config)


def set_remote_config(primary: str, secondary: str) -> None:
    config = load_config()
    config.remote = RemoteConfig(primary=primary, secondary=secondary)
    save_config(config)


def set_merge_mode(mode: str) -> None:
    if mode not in ("abort", "keep"):
        raise ValueError("merge_mode must be 'abort' or 'keep'")
    config = load_config()
    config.default_merge_mode = mode
    save_config(config)


def get_sibling_branches(name: str, repo) -> list:
    from branchs.core.branch import get_branch_fork_point

    fork_point = get_branch_fork_point(name, repo)
    if not fork_point:
        return []

    siblings = []
    for branch in repo.branches:
        if branch.name == name:
            continue
        bfork = get_branch_fork_point(branch.name, repo)
        if bfork == fork_point:
            siblings.append(branch.name)
    return siblings
