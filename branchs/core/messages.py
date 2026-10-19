"""Build Conventional Commits messages for the GUI."""

import re

COMMIT_TYPES = {
    "修复 Bug · fix": "fix",
    "新功能 · feat": "feat",
    "通用维护 · chore": "chore",
    "重构 · refactor": "refactor",
    "性能优化 · perf": "perf",
    "文档 · docs": "docs",
    "测试 · test": "test",
    "构建 · build": "build",
    "持续集成 · ci": "ci",
    "代码格式 · style": "style",
}


def suggest_scopes(repo) -> list[str]:
    """Offer common scopes and scopes inferred from this repository."""
    from branchs.core.commit import get_commit_history, get_staged_paths

    suggestions = ["gui", "cli", "core", "docs", "tests"]
    for path in get_staged_paths(repo):
        parts = path.replace("\\", "/").split("/")
        if parts[0] == "branchs" and len(parts) > 1:
            scope = "gui" if parts[1] == "gui.py" else ("cli" if parts[1] == "cli.py" else parts[1])
        elif parts[0].lower().startswith("readme") or parts[0] == "docs":
            scope = "docs"
        else:
            scope = parts[0].split(".")[0]
        if scope and scope not in suggestions:
            suggestions.append(scope)
    for commit in get_commit_history(repo, max_count=50):
        match = re.match(r"[a-z]+\(([^()]+)\)!?:", commit.message)
        if match and match.group(1) not in suggestions:
            suggestions.append(match.group(1))
    return suggestions


def build_commit_message(kind: str, summary: str, scope: str = "", body: str = "", breaking: bool = False) -> str:
    """Return a Conventional Commits message from explicit form fields."""
    if kind not in COMMIT_TYPES:
        raise ValueError("请选择提交类型")
    summary = summary.strip()
    scope = scope.strip()
    body = body.strip()
    if not summary or "\n" in summary:
        raise ValueError("请填写单行提交摘要")
    if scope and (any(char.isspace() for char in scope) or any(char in "():!" for char in scope)):
        raise ValueError("影响范围不能包含空格、括号、冒号或感叹号")
    subject = COMMIT_TYPES[kind] + (f"({scope})" if scope else "")
    subject += ("!" if breaking else "") + f": {summary}"
    if breaking and "BREAKING CHANGE:" not in body:
        body = (body + "\n\n" if body else "") + "BREAKING CHANGE: " + summary
    return subject + ("\n\n" + body if body else "")
