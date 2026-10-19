import pathlib
import subprocess
import tempfile
import unittest

import git

from branchs.core.remote import sync_remotes


def run(path, *args):
    return subprocess.run(["git", *args], cwd=path, check=True, text=True,
                          capture_output=True).stdout.strip()


class RemoteSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.primary = root / "primary.git"
        self.secondary = root / "secondary.git"
        self.work = root / "work"
        self.other = root / "other"
        run(root, "init", "--bare", str(self.primary))
        run(root, "init", "--bare", str(self.secondary))
        run(root, "clone", str(self.primary), str(self.work))
        self.identity(self.work)
        run(self.work, "remote", "add", "mirror", str(self.secondary))
        (self.work / "base.txt").write_text("base")
        run(self.work, "add", "base.txt")
        run(self.work, "commit", "-m", "base")
        run(self.work, "branch", "-M", "main")
        run(self.work, "push", "origin", "main")
        run(self.work, "push", "mirror", "main")
        self.base = run(self.work, "rev-parse", "HEAD")

    @staticmethod
    def identity(path):
        run(path, "config", "user.name", "Test")
        run(path, "config", "user.email", "test@example.com")

    def test_reports_each_branch_and_continues_after_divergence(self):
        run(self.work, "checkout", "-b", "conflict", self.base)
        run(self.work, "push", "origin", "conflict")
        run(self.work, "push", "mirror", "conflict")
        (self.work / "primary.txt").write_text("primary change")
        run(self.work, "add", "primary.txt")
        run(self.work, "commit", "-m", "primary conflict")
        run(self.work, "push", "origin", "conflict")

        run(self.work, "checkout", "main")
        (self.work / "main.txt").write_text("main change")
        run(self.work, "add", "main.txt")
        run(self.work, "commit", "-m", "update main")
        run(self.work, "push", "origin", "main")
        run(self.work, "checkout", "-b", "new")
        run(self.work, "push", "origin", "new")
        run(self.work, "checkout", "main")

        run(self.secondary.parent, "clone", str(self.secondary), str(self.other))
        self.identity(self.other)
        run(self.other, "checkout", "conflict")
        (self.other / "secondary.txt").write_text("secondary change")
        run(self.other, "add", "secondary.txt")
        run(self.other, "commit", "-m", "secondary conflict")
        run(self.other, "push", "origin", "conflict")
        secondary_conflict = run(self.other, "rev-parse", "HEAD")
        run(self.other, "checkout", "-b", "secondary-only")
        run(self.other, "push", "origin", "secondary-only")

        (self.work / "base.txt").write_text("local uncommitted work")
        report = sync_remotes(git.Repo(self.work), "origin", "mirror")

        self.assertEqual({item.branch for item in report.synced}, {"main", "new"})
        self.assertEqual({item.branch for item in report.failed}, {"conflict"})
        self.assertEqual(report.total, 3)
        self.assertEqual(run(self.work, "ls-remote", "mirror", "refs/heads/main").split()[0],
                         run(self.work, "ls-remote", "origin", "refs/heads/main").split()[0])
        self.assertEqual(run(self.work, "ls-remote", "mirror", "refs/heads/new").split()[0],
                         run(self.work, "ls-remote", "origin", "refs/heads/new").split()[0])
        self.assertEqual(run(self.work, "ls-remote", "mirror", "refs/heads/conflict").split()[0],
                         secondary_conflict)
        self.assertTrue(run(self.work, "ls-remote", "mirror", "refs/heads/secondary-only"))
        self.assertEqual(run(self.work, "branch", "--show-current"), "main")
        self.assertEqual(run(self.work, "branch", "--list", "_sync_*"), "")
        self.assertEqual((self.work / "base.txt").read_text(), "local uncommitted work")
        summary = report.summary()
        self.assertIn("Succeeded: 2", summary)
        self.assertIn("Failed: 1", summary)
        self.assertIn("[FAIL] conflict", summary)

    def test_already_current_branch_is_success(self):
        report = sync_remotes(git.Repo(self.work), "origin", "mirror")
        self.assertEqual([(item.branch, item.message) for item in report.synced],
                         [("main", "Already up to date")])
        self.assertFalse(report.failed)


if __name__ == "__main__":
    unittest.main()
