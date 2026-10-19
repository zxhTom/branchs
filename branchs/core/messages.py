"""Build Conventional Commits messages for the GUI."""

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
