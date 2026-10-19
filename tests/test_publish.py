import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import git

from branchs.core.config import BranchConfig, BranchType
from branchs.core.publish import publish_branch


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


if __name__ == "__main__":
    unittest.main()
