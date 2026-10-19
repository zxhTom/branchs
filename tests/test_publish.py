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
from branchs.core.publish import get_pending_files
from branchs.core.network import git_network


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

        result = publish_branch(git.Repo(self.local), message="my changes")

        self.assertTrue(result.success, result.message)
        self.assertEqual(run(self.local, "status", "--porcelain"), "")
        self.assertEqual(run(self.local, "rev-parse", "HEAD"), run(self.local, "ls-remote", "origin", "refs/heads/a").split()[0])
        self.assertEqual(
            set(run(self.local, "ls-tree", "-r", "--name-only", "HEAD").splitlines()),
            {"base", "b2", "a1", "a2", "staged", "untracked"},
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
        original_remote = run(self.local, "ls-remote", "origin", "refs/heads/a")

        result = publish_branch(git.Repo(self.local), message="should not commit")

        self.assertFalse(result.success)
        self.assertTrue((self.local / "untracked").exists())
        self.assertEqual(run(self.local, "ls-remote", "origin", "refs/heads/a"), original_remote)
        self.assertEqual(run(self.local, "status", "--porcelain"), "?? untracked")

    def test_preview_lists_staged_unstaged_and_untracked_files(self):
        (self.local / "staged").write_text("new")
        run(self.local, "add", "staged")
        (self.local / "base").write_text("edited")
        (self.local / "untracked").write_text("new")

        pending = get_pending_files(git.Repo(self.local))

        self.assertEqual(set(pending), {"A  staged", " M base", "?? untracked"})

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


if __name__ == "__main__":
    unittest.main()
