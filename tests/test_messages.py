import unittest

from branchs.core.messages import build_commit_message, suggest_scopes


class CommitMessageTests(unittest.TestCase):
    def test_conventional_subject_and_body(self):
        self.assertEqual(
            build_commit_message("修复 Bug · fix", "修复代理连接", "gui", "内网地址直连"),
            "fix(gui): 修复代理连接\n\n内网地址直连",
        )

    def test_breaking_change_footer(self):
        self.assertEqual(
            build_commit_message("新功能 · feat", "改用新接口", breaking=True),
            "feat!: 改用新接口\n\nBREAKING CHANGE: 改用新接口",
        )

    def test_requires_summary(self):
        with self.assertRaises(ValueError):
            build_commit_message("通用维护 · chore", "  ")

    def test_scope_suggestions_include_repository_history(self):
        class Commit:
            message = "fix(network): repair proxy"

        from unittest.mock import patch
        with patch("branchs.core.commit.get_staged_paths", return_value=["branchs/gui.py"]), \
             patch("branchs.core.commit.get_commit_history", return_value=[Commit()]):
            scopes = suggest_scopes(object())
        self.assertIn("gui", scopes)
        self.assertIn("network", scopes)


if __name__ == "__main__":
    unittest.main()
