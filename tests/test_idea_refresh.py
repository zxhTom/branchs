import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import git

from branchs.core.idea import get_active_changelist, pending_changes_signature, stage_idea_changes
from branchs.gui import BranchManagerGUI


class IdeaRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.repo = git.Repo.init(self.path)
        self.addCleanup(self.repo.close)
        with self.repo.config_writer() as config:
            config.set_value('user', 'name', 'Test')
            config.set_value('user', 'email', 'test@example.com')
        for name in ('current.txt', 'other.txt'):
            (self.path / name).write_text('base')
        self.repo.index.add(['current.txt', 'other.txt'])
        self.repo.index.commit('base')
        (self.path / '.idea').mkdir()
        self.workspace = self.path / '.idea/workspace.xml'
        self.snapshot()

    def snapshot(self, current=(), other=()):
        def entries(paths):
            return ''.join(f'<change afterPath="$PROJECT_DIR$/{p}" />' for p in paths)
        self.workspace.write_text(
            '<project><component name="ChangeListManager">'
            f'<list name="Changes" default="true">{entries(current)}</list>'
            f'<list name="Other">{entries(other)}</list>'
            '</component></project>'
        )

    def test_unsaved_idea_snapshot_exposes_changes_without_assigning_them(self):
        (self.path/'current.txt').write_text('edited')
        (self.path/'untracked.txt').write_text('not tracked')
        s = get_active_changelist(self.repo)
        self.assertEqual(s.visible_paths, [])
        self.assertEqual(s.paths, [])
        self.assertEqual(s.unassigned_paths, ['current.txt'])
        with self.assertRaises(ValueError):
            stage_idea_changes(self.repo, ['current.txt'])
        self.assertEqual(self.repo.git.diff('--cached', '--name-only'), '')

    def test_other_changelist_is_never_shown_as_unsynced_current_files(self):
        self.snapshot(other=['other.txt'])
        (self.path/'current.txt').write_text('current edit')
        (self.path/'other.txt').write_text('other edit')
        s = get_active_changelist(self.repo)
        self.assertEqual(s.visible_paths, [])
        self.assertEqual(s.unassigned_paths, ['current.txt'])

    def test_saved_idea_snapshot_resolves_unsynced_files(self):
        (self.path/'current.txt').write_text('edited')
        before = pending_changes_signature(self.repo)
        self.assertEqual(get_active_changelist(self.repo).unassigned_paths, ['current.txt'])
        self.snapshot(current=['current.txt'])
        self.assertNotEqual(before, pending_changes_signature(self.repo))
        s = get_active_changelist(self.repo)
        self.assertEqual(s.visible_paths, ['current.txt'])
        self.assertEqual(s.unassigned_paths, [])
        self.assertEqual(s.paths, [])

    def test_git_edit_staging_and_clean_state_change_signature(self):
        initial = pending_changes_signature(self.repo)
        (self.path/'current.txt').write_text('edited')
        modified = pending_changes_signature(self.repo)
        self.assertNotEqual(initial, modified)
        self.repo.index.add(['current.txt'])
        self.assertNotEqual(modified, pending_changes_signature(self.repo))

    def make_gui(self):
        gui = object.__new__(BranchManagerGUI)
        gui.repo = self.repo
        gui._publish_busy = False
        gui._pending_signature = None
        gui._pending_focus_job = None
        gui._refresh_pending_files = Mock()
        gui.pending_hint_var = Mock()
        gui.root = Mock()
        return gui

    def test_poll_refreshes_new_file_and_idea_save_without_manual_click(self):
        gui = self.make_gui()
        gui._check_pending_files()
        gui._check_pending_files()
        self.assertEqual(gui._refresh_pending_files.call_count, 1)
        (self.path/'current.txt').write_text('new tracked edit')
        gui._check_pending_files()
        self.assertEqual(gui._refresh_pending_files.call_count, 2)
        self.snapshot(current=['current.txt'])
        gui._check_pending_files()
        self.assertEqual(gui._refresh_pending_files.call_count, 3)

    def test_publish_pauses_refresh(self):
        gui = self.make_gui()
        gui._publish_busy = True
        gui._check_pending_files()
        gui._refresh_pending_files.assert_not_called()

    def test_transient_error_does_not_stop_watcher(self):
        gui = self.make_gui()
        with patch('branchs.gui.pending_changes_signature', side_effect=OSError('temporary lock')):
            gui._watch_pending_files()
        gui.root.after.assert_called_with(3000, gui._watch_pending_files)
        gui._check_pending_files()
        gui._refresh_pending_files.assert_called_once()

    def test_render_failure_retries_even_with_unchanged_signature(self):
        gui = self.make_gui()
        gui._refresh_pending_files.side_effect = [False, True]
        gui._check_pending_files()
        self.assertIsNone(gui._pending_signature)
        gui._check_pending_files()
        self.assertEqual(gui._refresh_pending_files.call_count, 2)
        self.assertIsNotNone(gui._pending_signature)

    def test_focus_checks_are_debounced(self):
        gui = self.make_gui()
        gui._pending_files_focus()
        previous = gui._pending_focus_job
        gui._pending_files_focus()
        gui.root.after_cancel.assert_called_with(previous)
        gui.root.after.assert_called_with(150, gui._check_pending_files)

    def test_gui_renders_unsynced_then_resolves_without_losing_description(self):
        import tkinter as tk
        from branchs.core.config import Config
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch('branchs.gui.startup_repository', return_value=self.repo), patch('branchs.gui.remember_repo'), patch('branchs.gui.load_config', return_value=Config()):
            gui = BranchManagerGUI(root)
        gui.commit_summary_var.set('keep this summary')
        gui.commit_body_text.insert('1.0', 'keep this body')
        (self.path/'current.txt').write_text('edited')
        root.after(1600, root.quit)
        root.mainloop()  # The scheduled watcher, not a manual refresh, finds the edit.
        rows = [gui.pending_files_tree.item(i, 'values') for i in gui.pending_files_tree.get_children()]
        self.assertIn(('NOT SYNCED', 'current.txt'), rows)
        self.snapshot(current=['current.txt'])
        gui._check_pending_files()
        rows = [gui.pending_files_tree.item(i, 'values') for i in gui.pending_files_tree.get_children()]
        self.assertIn(('ADD FIRST', 'current.txt'), rows)
        self.assertNotIn(('NOT SYNCED', 'current.txt'), rows)
        self.assertEqual(gui.commit_summary_var.get(), 'keep this summary')
        self.assertEqual(gui.commit_body_text.get('1.0','end-1c'), 'keep this body')
        self.assertEqual(self.repo.git.diff('--cached','--name-only'), '')


if __name__ == '__main__':
    unittest.main()