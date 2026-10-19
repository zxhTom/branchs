import unittest

from branchs.core.messages import build_commit_message


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


if __name__ == "__main__":
    unittest.main()
