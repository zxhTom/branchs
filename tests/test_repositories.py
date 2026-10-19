import pathlib
import tempfile
import unittest
from unittest.mock import patch

import git

from branchs.core.config import load_config, remember_repo
from branchs.core.repositories import open_repository, startup_repository


class RepositorySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        config_dir = self.root / "config"
        patches = [
            patch("branchs.core.config.CONFIG_DIR", str(config_dir)),
            patch("branchs.core.config.CONFIG_FILE", str(config_dir / "config.json")),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.first = self.root / "first"
        self.second = self.root / "second"
        git.Repo.init(self.first)
        git.Repo.init(self.second)

    def test_remembers_last_and_recent_repositories(self):
        remember_repo(str(self.first))
        remember_repo(str(self.second))
        remember_repo(str(self.first))

        config = load_config()
        self.assertEqual(config.last_repo, str(self.first))
        self.assertEqual(config.recent_repos, [str(self.first), str(self.second)])
        self.assertEqual(startup_repository().working_tree_dir, str(self.first))

    def test_missing_last_repo_falls_back_to_recent(self):
        remember_repo(str(self.second))
        remember_repo(str(self.first))
        self.first.rename(self.root / "moved")

        self.assertEqual(startup_repository().working_tree_dir, str(self.second))

    def test_open_repository_accepts_subfolder_and_rejects_non_repo(self):
        nested = self.first / "nested"
        nested.mkdir()

        self.assertEqual(open_repository(str(nested)).working_tree_dir, str(self.first))
        with self.assertRaises(ValueError):
            open_repository(str(self.root / "config"))


if __name__ == "__main__":
    unittest.main()
