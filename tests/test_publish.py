import pathlib
import subprocess
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

import git

from branchs.core.config import BranchConfig, BranchType
from branchs.core.publish import publish_branch
from branchs.core.publish import get_publish_selection
from branchs.core.commit import commit_changes
from branchs.core.network import git_network
from branchs.core.idea import commit_active_changelist, get_active_changelist, stage_idea_changes


def run(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.remote = root / "remote.git"
        self.local = root / "local"
        self.other = root / "other"
        run(root, "init", "--bare", str(self.remote))
        run(root, "clone", str(self.remote), str(self.local))
        self.identity(self.local)
        self.write_commit(self.local, "base", "base")
        run(self.local, "branch", "-M", "b")
        run(self.local, "push", "-u", "origin", "b")
        run(self.local, "checkout", "-b", "a")
        self.write_commit(self.local, "a1", "a1")
        run(self.local, "push", "-u", "origin", "a")
        run(root, "clone", str(self.remote), str(self.other))
        self.identity(self.other)
        run(self.other, "checkout", "a")
        self.config = patch(
            "branchs.core.publish.get_branch_config",
            return_value=BranchConfig("a", BranchType.FEATURE, "b"),
        )
        self.config.start()
        self.addCleanup(self.config.stop)

    @staticmethod
    def identity(path):
        run(path, "config", "user.name", "Test")
        run(path, "config", "user.email", "test@example.com")

    @staticmethod
    def write_commit(path, name, content):
        (path / name).write_text(content)
        run(path, "add", name)
        run(path, "commit", "-m", name)

    def test_syncs_remote_a_before_rebasing_b_and_restores_changes(self):
        self.write_commit(self.other, "a2", "a2")
        run(self.other, "push", "origin", "a")
        run(self.other, "checkout", "b")
        self.write_commit(self.other, "b2", "b2")
        run(self.other, "push", "origin", "b")
        (self.local / "staged").write_text("staged")
        run(self.local, "add", "staged")
        (self.local / "untracked").write_text("untracked")

        stages = []
        result = publish_branch(git.Repo(self.local), message="my changes", mode="all", progress=stages.append)

        self.assertTrue(result.success, result.message)
        self.assertTrue(any("获取" in stage for stage in stages))
        self.assertTrue(any("推送" in stage for stage in stages))
        self.assertEqual(run(self.local, "status", "--porcelain"), "?? untracked")
        self.assertEqual(run(self.local, "rev-parse", "HEAD"), run(self.local, "ls-remote", "origin", "refs/heads/a").split()[0])
        self.assertEqual(
            set(run(self.local, "ls-tree", "-r", "--name-only", "HEAD").splitlines()),
            {"base", "b2", "a1", "a2", "staged"},
        )
        self.assertEqual(run(self.local, "log", "-1", "--format=%s"), "my changes")

    def test_rebase_conflict_stops_before_commit_or_push(self):
        run(self.other, "checkout", "b")
        (self.other / "base").write_text("parent version")
        run(self.other, "commit", "-am", "change parent")
        run(self.other, "push", "origin", "b")
        (self.local / "base").write_text("local version")
        run(self.local, "commit", "-am", "change local")
        (self.local / "untracked").write_text("keep me")
        run(self.local, "add", "untracked")
        original_remote = run(self.local, "ls-remote", "origin", "refs/heads/a")

        result = publish_branch(git.Repo(self.local), message="should not commit", mode="all")

        self.assertFalse(result.success)
        self.assertTrue((self.local / "untracked").exists())
        self.assertEqual(run(self.local, "ls-remote", "origin", "refs/heads/a"), original_remote)
        self.assertEqual(run(self.local, "status", "--porcelain"), "A  untracked")

    def test_preview_lists_only_staged_files(self):
        (self.local / "staged").write_text("new")
        run(self.local, "add", "staged")
        (self.local / "base").write_text("edited")
        (self.local / "untracked").write_text("new")

        selection = get_publish_selection(git.Repo(self.local), "all")

        self.assertEqual(selection.paths, ["staged"])
        self.assertEqual(selection.display, ["A\tstaged"])

    def test_commit_does_not_add_unstaged_files(self):
        (self.local / "base").write_text("changed")
        (self.local / "untracked").write_text("new")

        success, message = commit_changes(git.Repo(self.local), message="must not commit")

        self.assertFalse(success)
        self.assertIn("No staged changes", message)
        self.assertEqual(run(self.local, "diff", "--cached", "--name-only"), "")

    def test_network_commands_override_git_http_proxy_without_changing_config(self):
        run(self.local, "config", "http.proxy", "http://proxy.invalid:8080")
        run(self.local, "config", "remote.origin.proxy", "http://remote-proxy.invalid:8080")
        repo = git.Repo(self.local)
        with git_network(repo):
            self.assertEqual(repo.git.config("--get", "http.proxy"), "")
            self.assertEqual(repo.git.config("--get", "remote.origin.proxy"), "")
        self.assertEqual(repo.git.config("--get", "http.proxy"), "http://proxy.invalid:8080")

    def test_http_remote_never_contacts_configured_proxy(self):
        run(self.remote, "update-server-info")
        root = self.remote.parent
        proxy_requests = []

        class Origin(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, *args):
                pass

        class Proxy(BaseHTTPRequestHandler):
            def do_GET(self):
                proxy_requests.append(self.path)
                self.send_error(503)

            def log_message(self, *args):
                pass

        origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        threads = [Thread(target=server.serve_forever, daemon=True) for server in (origin, proxy)]
        for thread in threads:
            thread.start()
        self.addCleanup(lambda: [server.server_close() for server in (origin, proxy)])
        self.addCleanup(lambda: [thread.join() for thread in threads])
        self.addCleanup(lambda: [server.shutdown() for server in (origin, proxy)])

        url = f"http://127.0.0.1:{origin.server_port}/remote.git"
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        repo = git.Repo(self.local)
        repo.git.remote("set-url", "origin", url)
        repo.git.config("http.proxy", proxy_url)
        repo.git.config(f"http.{url}.proxy", proxy_url)
        proxy_env = {name: proxy_url for name in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"
        )}
        proxy_env.update(NO_PROXY="", no_proxy="")
        with patch.dict("os.environ", proxy_env):
            with self.assertRaises(git.GitCommandError):
                repo.git.ls_remote("--heads", "origin")
            self.assertEqual(len(proxy_requests), 1)
            with git_network(repo):
                self.assertIn("refs/heads/a", repo.git.ls_remote("--heads", "origin"))
            self.assertEqual(len(proxy_requests), 1)

    def write_idea_changelists(self, active_paths, other_paths=()):
        idea = self.local / ".idea"
        idea.mkdir(exist_ok=True)
        def changes(paths):
            return "".join(
                f'<change beforePath="$PROJECT_DIR$/{path}" afterPath="$PROJECT_DIR$/{path}" />'
                for path in paths
            )
        (idea / "workspace.xml").write_text(
            '<project><component name="ChangeListManager">'
            f'<list name="Current" default="true">{changes(active_paths)}</list>'
            f'<list name="Other">{changes(other_paths)}</list>'
            '</component></project>'
        )

    def test_idea_mode_commits_only_active_changelist(self):
        self.write_idea_changelists(["base"], ["a1"])
        (self.local / "base").write_text("selected")
        run(self.local, "add", "base")
        (self.local / "a1").write_text("not selected")
        (self.local / "untracked").write_text("not selected")

        selected = get_active_changelist(git.Repo(self.local))
        success, message = commit_active_changelist(git.Repo(self.local), "selected commit")

        self.assertEqual(selected.paths, ["base"])
        self.assertEqual(selected.visible_paths, ["base"])
        self.assertTrue(success, message)
        self.assertEqual(run(self.local, "show", "--pretty=format:", "--name-only", "HEAD"), "base")
        self.assertIn(" M a1", subprocess.run(
            ["git", "status", "--short"], cwd=self.local, check=True, text=True, capture_output=True
        ).stdout)
        self.assertIn("?? untracked", run(self.local, "status", "--short"))

    def test_idea_mode_rejects_file_split_across_changelists(self):
        self.write_idea_changelists(["base"], ["base"])
        (self.local / "base").write_text("changed")
        with self.assertRaisesRegex(ValueError, "splits these files"):
            get_active_changelist(git.Repo(self.local))

    def test_idea_mode_displays_unstaged_tracked_changes(self):
        self.write_idea_changelists(["base", "untracked"])
        (self.local / "base").write_text("edited, not staged")
        (self.local / "untracked").write_text("not tracked")

        selected = get_active_changelist(git.Repo(self.local))

        self.assertEqual(selected.visible_paths, ["base"])
        self.assertEqual(selected.paths, [])
        self.assertEqual(run(self.local, "diff", "--cached", "--name-only"), "")

    def test_confirmed_idea_staging_only_adds_requested_changelist_file(self):
        self.write_idea_changelists(["base"], ["a1"])
        (self.local / "base").write_text("ready after explicit confirmation")
        (self.local / "a1").write_text("not selected")
        (self.local / "untracked").write_text("not tracked")
        repo = git.Repo(self.local)

        stage_idea_changes(repo, ["base"])

        self.assertEqual(run(self.local, "diff", "--cached", "--name-only"), "base")
        self.assertEqual(get_publish_selection(repo, "idea").paths, ["base"])
        with self.assertRaisesRegex(ValueError, "changed since confirmation"):
            stage_idea_changes(repo, ["a1"])

    def test_confirmed_idea_changes_publish_after_staging(self):
        self.write_idea_changelists(["base"])
        (self.local / "base").write_text("edited in IDEA")
        repo = git.Repo(self.local)
        self.assertEqual(get_active_changelist(repo).visible_paths, ["base"])
        self.assertEqual(get_publish_selection(repo, "idea").paths, [])

        stage_idea_changes(repo, ["base"])
        result = publish_branch(repo, message="fix(core): publish IDEA changes", mode="idea")

        self.assertTrue(result.success, result.message)
        self.assertEqual(run(self.local, "show", "--pretty=format:", "--name-only", "HEAD"), "base")
        self.assertEqual(run(self.local, "rev-parse", "HEAD"),
                         run(self.local, "ls-remote", "origin", "refs/heads/a").split()[0])

    def test_idea_mode_reads_windows_style_project_paths(self):
        self.write_idea_changelists([])
        workspace = self.local / ".idea" / "workspace.xml"
        workspace.write_text(
            '<project><component name="ChangeListManager">'
            '<list name="Changes" default="true">'
            '<change beforePath="$PROJECT_DIR$\\base" afterPath="$PROJECT_DIR$\\base" />'
            '</list></component></project>'
        )
        (self.local / "base").write_text("modified")

        self.assertEqual(get_active_changelist(git.Repo(self.local)).visible_paths, ["base"])

    def test_idea_project_in_child_directory_is_found(self):
        child = self.local / "module"
        child.mkdir()
        idea = child / ".idea"
        idea.mkdir()
        (idea / "workspace.xml").write_text(
            '<project><component name="ChangeListManager">'
            '<list name="Changes" default="true">'
            '<change beforePath="$PROJECT_DIR$/../base" afterPath="$PROJECT_DIR$/../base" />'
            '</list></component></project>'
        )
        (self.local / "base").write_text("modified")

        self.assertEqual(get_active_changelist(git.Repo(self.local)).visible_paths, ["base"])

    def test_add_mode_uses_only_git_index(self):
        self.write_idea_changelists(["a1"])
        (self.local / "base").write_text("staged")
        run(self.local, "add", "base")
        (self.local / "a1").write_text("unstaged")

        selected = get_publish_selection(git.Repo(self.local), mode="add")

        self.assertEqual(selected.paths, ["base"])
        self.assertEqual(selected.display, ["M\tbase"])

    def test_idea_mode_does_not_fall_back_to_all_changes_without_idea_data(self):
        (self.local / "base").write_text("changed")
        (self.local / "untracked").write_text("not selected")
        original_head = run(self.local, "rev-parse", "HEAD")

        result = publish_branch(git.Repo(self.local), message="must not commit")

        self.assertFalse(result.success)
        self.assertIn("IDEA project not found", result.message)
        self.assertEqual(run(self.local, "rev-parse", "HEAD"), original_head)
        self.assertEqual(run(self.local, "status", "--short"), "M base\n?? untracked")

    def test_idea_publish_leaves_other_changes_uncommitted(self):
        self.write_idea_changelists(["base"], ["a1"])
        (self.local / "base").write_text("selected")
        run(self.local, "add", "base")
        (self.local / "a1").write_text("other changelist")
        (self.local / "untracked").write_text("not selected")

        result = publish_branch(git.Repo(self.local), message="selected publish")

        self.assertTrue(result.success, result.message)
        self.assertEqual(run(self.local, "show", "--pretty=format:", "--name-only", "HEAD"), "base")
        status = run(self.local, "status", "--short")
        self.assertIn("M a1", status)
        self.assertIn("?? untracked", status)

    def test_idea_mode_rejects_staged_files_outside_active_changelist(self):
        self.write_idea_changelists(["base"], ["a1"])
        (self.local / "base").write_text("selected")
        run(self.local, "add", "base")
        (self.local / "a1").write_text("other")
        run(self.local, "add", "a1")

        result = publish_branch(git.Repo(self.local), message="must not commit")

        self.assertFalse(result.success)
        self.assertIn("outside the active IDEA changelist", result.message)
        self.assertEqual(run(self.local, "ls-remote", "origin", "refs/heads/a").split()[0], run(self.local, "rev-parse", "HEAD"))

    def test_idea_mode_commits_staged_content_only(self):
        self.write_idea_changelists(["base"])
        (self.local / "base").write_text("staged version")
        run(self.local, "add", "base")
        (self.local / "base").write_text("later unstaged version")

        success, message = commit_active_changelist(git.Repo(self.local), "index only")

        self.assertTrue(success, message)
        self.assertEqual(run(self.local, "show", "HEAD:base"), "staged version")
        self.assertEqual((self.local / "base").read_text(), "later unstaged version")


if __name__ == "__main__":
    unittest.main()
