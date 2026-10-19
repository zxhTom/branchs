import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

import git

from branchs.core.branch import (
    merge_branch,
    rebase_branch,
    get_sibling_branches,
    get_diff_between_branches,
    MergeResult,
    RebaseResult,
)
from branchs.core.commit import (
    commit_changes,
    get_commit_history,
    cherry_pick_commit,
    generate_commit_message,
)
from branchs.core.config import (
    BranchType,
    load_config,
    save_config,
    set_branch_config,
    set_default_branch,
    set_remote_config,
    BranchConfig,
)
from branchs.core.git import (
    get_repo,
    get_current_branch,
    list_branches,
    list_remotes,
    get_remotes_info,
    has_uncommitted_changes,
    fetch_all,
    rebase_abort,
    rebase_continue,
    rebase_skip,
    is_rebasing,
)
from branchs.core.remote import sync_remotes
from branchs.core.publish import publish_branch

MODE_OPTIONS = ["abort", "keep"]
BRANCH_TYPE_OPTIONS = [t.value for t in BranchType]


class BranchManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Branchs - Branch Manager")
        self.root.geometry("1024x768")

        self._branch_combos = []
        self._remote_combos = []

        try:
            self.repo = get_repo()
        except Exception:
            self.repo = None

        self._create_menu()
        self._create_main_view()
        self._refresh()

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Repo", command=self._open_repo)
        file_menu.add_command(label="Refresh", command=self._refresh)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Branchs v0.1.0"))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _create_main_view(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._create_branch_tab()
        self._create_merge_tab()
        self._create_rebase_tab()
        self._create_commit_tab()
        self._create_remote_tab()
        self._create_config_tab()

    def _create_branch_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Branches")

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Refresh", command=self._refresh_branch_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Fetch All", command=self._fetch_all).pack(side=tk.LEFT, padx=2)

        columns = ("name", "type", "upstream", "current")
        self.branch_tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.branch_tree.heading("name", text="Branch")
        self.branch_tree.heading("type", text="Type")
        self.branch_tree.heading("upstream", text="Upstream")
        self.branch_tree.heading("current", text="Current")

        self.branch_tree.column("name", width=200)
        self.branch_tree.column("type", width=100)
        self.branch_tree.column("upstream", width=200)
        self.branch_tree.column("current", width=60)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.branch_tree.yview)
        self.branch_tree.configure(yscrollcommand=scrollbar.set)

        self.branch_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.branch_tree.bind("<Double-1>", self._on_branch_double_click)
        self.branch_tree.bind("<Button-3>", self._on_branch_right_click)

        detail_frame = ttk.LabelFrame(frame, text="Branch Details")
        detail_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(detail_frame, text="Type:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.branch_type_var = tk.StringVar()
        type_combo = ttk.Combobox(detail_frame, textvariable=self.branch_type_var, values=BRANCH_TYPE_OPTIONS)
        type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(detail_frame, text="Upstream:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.upstream_var = tk.StringVar()
        self.upstream_combo = ttk.Combobox(detail_frame, textvariable=self.upstream_var, width=28)
        self.upstream_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)
        self._branch_combos.append(self.upstream_combo)

        ttk.Button(detail_frame, text="Save Config", command=self._save_branch_config).grid(row=0, column=4, padx=5)
        ttk.Button(detail_frame, text="Set as Default", command=self._set_default_from_gui).grid(row=0, column=5, padx=5)

    def _create_merge_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Merge")

        ttk.Label(frame, text="Source Branch:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.merge_source_var = tk.StringVar()
        self.merge_source_combo = ttk.Combobox(frame, textvariable=self.merge_source_var, width=28)
        self.merge_source_combo.grid(row=0, column=1, padx=5, pady=5)
        self._branch_combos.append(self.merge_source_combo)
        ttk.Button(frame, text="Use Default", command=self._use_default_source).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="Target Branch:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.merge_target_var = tk.StringVar()
        self.merge_target_combo = ttk.Combobox(frame, textvariable=self.merge_target_var, width=28)
        self.merge_target_combo.grid(row=1, column=1, padx=5, pady=5)
        self._branch_combos.append(self.merge_target_combo)

        ttk.Label(frame, text="Conflict Mode:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.merge_mode_var = tk.StringVar(value="abort")
        ttk.Combobox(frame, textvariable=self.merge_mode_var, values=MODE_OPTIONS, state="readonly").grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=5
        )

        self.merge_noff_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="No fast-forward", variable=self.merge_noff_var).grid(
            row=2, column=2, sticky=tk.W, padx=5
        )

        ttk.Button(frame, text="Merge", command=self._do_merge).grid(row=3, column=0, columnspan=2, pady=10)

        self.merge_output = scrolledtext.ScrolledText(frame, height=20, width=80)
        self.merge_output.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        frame.grid_rowconfigure(4, weight=1)
        frame.grid_columnconfigure(1, weight=1)

    def _create_rebase_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Rebase")

        ttk.Label(frame, text="Current / Branch to Rebase:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.rebase_branch_var = tk.StringVar()
        self.rebase_branch_combo = ttk.Combobox(frame, textvariable=self.rebase_branch_var, width=28)
        self.rebase_branch_combo.grid(row=0, column=1, padx=5, pady=5)
        self._branch_combos.append(self.rebase_branch_combo)
        ttk.Button(frame, text="Use Current", command=self._use_current_branch_for_rebase).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="Upstream (Rebase onto):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.rebase_upstream_var = tk.StringVar()
        self.rebase_upstream_combo = ttk.Combobox(frame, textvariable=self.rebase_upstream_var, width=28)
        self.rebase_upstream_combo.grid(row=1, column=1, padx=5, pady=5)
        self._branch_combos.append(self.rebase_upstream_combo)

        ttk.Label(frame, text="Conflict Mode:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.rebase_mode_var = tk.StringVar(value="abort")
        ttk.Combobox(frame, textvariable=self.rebase_mode_var, values=MODE_OPTIONS, state="readonly").grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=5
        )

        btn_box = ttk.Frame(frame)
        btn_box.grid(row=3, column=0, columnspan=3, pady=10)

        ttk.Button(btn_box, text="Rebase", command=self._do_rebase).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="Continue", command=self._rebase_continue).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="Skip", command=self._rebase_skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="Abort", command=self._rebase_abort).pack(side=tk.LEFT, padx=5)

        self.rebase_output = scrolledtext.ScrolledText(frame, height=20, width=80)
        self.rebase_output.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        frame.grid_rowconfigure(4, weight=1)
        frame.grid_columnconfigure(1, weight=1)


    def _create_commit_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Commit")

        ttk.Label(frame, text="Commit Message:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.commit_msg_var = tk.StringVar()
        msg_entry = ttk.Entry(frame, textvariable=self.commit_msg_var, width=60)
        msg_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=5)

        ttk.Button(btn_frame, text="Suggest Message", command=self._suggest_commit_message).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Commit All", command=self._commit_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Publish (Sync, Commit & Push)", command=self._publish_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh History", command=self._refresh_commit_history).pack(side=tk.LEFT, padx=2)

        columns = ("hash", "author", "date", "message")
        self.commit_tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        self.commit_tree.heading("hash", text="Hash")
        self.commit_tree.heading("author", text="Author")
        self.commit_tree.heading("date", text="Date")
        self.commit_tree.heading("message", text="Message")

        self.commit_tree.column("hash", width=80)
        self.commit_tree.column("author", width=150)
        self.commit_tree.column("date", width=100)
        self.commit_tree.column("message", width=400)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.commit_tree.yview)
        self.commit_tree.configure(yscrollcommand=scrollbar.set)

        self.commit_tree.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        scrollbar.grid(row=2, column=3, sticky="ns")

        cp_frame = ttk.LabelFrame(frame, text="Cherry-pick")
        cp_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        ttk.Label(cp_frame, text="Target:").pack(side=tk.LEFT, padx=2)
        self.cp_target_var = tk.StringVar()
        self.cp_target_combo = ttk.Combobox(cp_frame, textvariable=self.cp_target_var, width=18)
        self.cp_target_combo.pack(side=tk.LEFT, padx=2)
        self._branch_combos.append(self.cp_target_combo)
        ttk.Button(cp_frame, text="Cherry-pick Selected", command=self._cherry_pick_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(cp_frame, text="Revert Selected", command=self._revert_selected).pack(side=tk.LEFT, padx=5)

        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(1, weight=1)

    def _create_remote_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Remote Sync")

        # Top section: Remotes list
        remotes_frame = ttk.LabelFrame(frame, text="Detected Remotes")
        remotes_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        toolbar = ttk.Frame(remotes_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(toolbar, text="Scan / Refresh Remotes", command=self._refresh_remote_list).pack(side=tk.LEFT, padx=2)

        columns = ("name", "url")
        self.remote_tree = ttk.Treeview(remotes_frame, columns=columns, show="headings", height=5)
        self.remote_tree.heading("name", text="Remote Name")
        self.remote_tree.heading("url", text="URL")
        self.remote_tree.column("name", width=120)
        self.remote_tree.column("url", width=400)

        remote_scroll = ttk.Scrollbar(remotes_frame, orient=tk.VERTICAL, command=self.remote_tree.yview)
        self.remote_tree.configure(yscrollcommand=remote_scroll.set)
        self.remote_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        remote_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Middle section: Sync configuration
        sync_frame = ttk.LabelFrame(frame, text="Sync Settings")
        sync_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(sync_frame, text="Primary Remote:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.primary_remote_var = tk.StringVar(value="origin")
        self.primary_remote_combo = ttk.Combobox(sync_frame, textvariable=self.primary_remote_var, width=28)
        self.primary_remote_combo.grid(row=0, column=1, padx=5, pady=5)
        self._remote_combos.append(self.primary_remote_combo)

        ttk.Label(sync_frame, text="Secondary Remote:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.secondary_remote_var = tk.StringVar(value="upstream")
        self.secondary_remote_combo = ttk.Combobox(sync_frame, textvariable=self.secondary_remote_var, width=28)
        self.secondary_remote_combo.grid(row=1, column=1, padx=5, pady=5)
        self._remote_combos.append(self.secondary_remote_combo)

        btn_box = ttk.Frame(sync_frame)
        btn_box.grid(row=2, column=0, columnspan=3, pady=5)
        ttk.Button(btn_box, text="Save as Config", command=self._save_remote_config_from_gui).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="Sync", command=self._do_sync).pack(side=tk.LEFT, padx=5)

        # Bottom section: Output
        self.remote_output = scrolledtext.ScrolledText(frame, height=15, width=80)
        self.remote_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _create_config_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Config")

        config = load_config()

        ttk.Label(frame, text="Default Branch:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.default_branch_var = tk.StringVar(value=config.default_branch or "")
        self.default_branch_combo = ttk.Combobox(frame, textvariable=self.default_branch_var, width=28)
        self.default_branch_combo.grid(row=0, column=1, padx=5)
        self._branch_combos.append(self.default_branch_combo)
        ttk.Button(frame, text="Save", command=self._save_config).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="Merge Mode:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.config_mode_var = tk.StringVar(value=config.default_merge_mode)
        ttk.Combobox(frame, textvariable=self.config_mode_var, values=MODE_OPTIONS, state="readonly").grid(
            row=1, column=1, sticky=tk.W, padx=5
        )

    def _refresh(self):
        if self.repo:
            self._refresh_branch_list()
            self._refresh_remote_list()
            self._refresh_commit_history()
            self._refresh_dropdowns()

    def _refresh_branch_list(self):
        if not self.repo:
            return
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)

        config = load_config()
        current = get_current_branch(self.repo)
        for name in list_branches(self.repo):
            bc = config.branches.get(name)
            btype = bc.branch_type.value if bc else "-"
            upstream = bc.upstream if bc and bc.upstream else "-"
            mark = "●" if name == current else ""
            self.branch_tree.insert("", tk.END, values=(name, btype, upstream, mark))

    def _refresh_remote_list(self):
        if not self.repo:
            return
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)

        remotes = get_remotes_info(self.repo)
        remote_names = [r["name"] for r in remotes]
        for r in remotes:
            self.remote_tree.insert("", tk.END, values=(r["name"], r["url"]))

        for combo in self._remote_combos:
            combo["values"] = remote_names

        config = load_config()
        if config.remote and config.remote.primary in remote_names:
            self.primary_remote_var.set(config.remote.primary)
            self.secondary_remote_var.set(config.remote.secondary or "")
        else:
            if not self.primary_remote_var.get() or self.primary_remote_var.get() not in remote_names:
                if "origin" in remote_names:
                    self.primary_remote_var.set("origin")
                elif remote_names:
                    self.primary_remote_var.set(remote_names[0])
            if not self.secondary_remote_var.get() or self.secondary_remote_var.get() not in remote_names:
                if "upstream" in remote_names:
                    self.secondary_remote_var.set("upstream")
                elif len(remote_names) > 1:
                    remaining = [name for name in remote_names if name != self.primary_remote_var.get()]
                    if remaining:
                        self.secondary_remote_var.set(remaining[0])

    def _refresh_dropdowns(self):
        if not self.repo:
            return
        branch_names = list_branches(self.repo)
        branch_names.sort()
        for combo in self._branch_combos:
            combo["values"] = branch_names

        remote_names = list_remotes(self.repo)
        remote_names.sort()
        for combo in self._remote_combos:
            combo["values"] = remote_names

    def _refresh_commit_history(self):
        if not self.repo:
            return
        for item in self.commit_tree.get_children():
            self.commit_tree.delete(item)

        commits = get_commit_history(self.repo, max_count=50)
        for c in commits:
            self.commit_tree.insert(
                "", tk.END, values=(c.hash[:8], c.author, c.date.strftime("%Y-%m-%d"), c.message[:60])
            )


    def _fetch_all(self):
        if self.repo:
            fetch_all(self.repo)
            self._refresh_branch_list()
            messagebox.showinfo("Done", "Fetched all remotes")

    def _on_branch_double_click(self, event):
        sel = self.branch_tree.selection()
        if sel:
            item = self.branch_tree.item(sel[0])
            values = item["values"]
            if values and self.repo:
                branch_name = values[0]
                siblings = get_sibling_branches(branch_name, self.repo)
                if siblings:
                    messagebox.showinfo("Siblings", f"Siblings of '{branch_name}':\n" + "\n".join(siblings))
                else:
                    messagebox.showinfo("Siblings", f"No sibling branches for '{branch_name}'")

    def _on_branch_right_click(self, event):
        pass

    def _save_branch_config(self):
        sel = self.branch_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a branch first")
            return

        item = self.branch_tree.item(sel[0])
        branch_name = item["values"][0]
        btype_str = self.branch_type_var.get()
        upstream = self.upstream_var.get() or None

        if btype_str not in BRANCH_TYPE_OPTIONS:
            messagebox.showwarning("Warning", f"Invalid branch type: {btype_str}")
            return

        try:
            set_branch_config(branch_name, BranchType(btype_str), upstream)
            self._refresh_branch_list()
            messagebox.showinfo("Done", f"Branch '{branch_name}' updated")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _set_default_from_gui(self):
        sel = self.branch_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a branch first")
            return

        item = self.branch_tree.item(sel[0])
        branch_name = item["values"][0]
        set_default_branch(branch_name)
        messagebox.showinfo("Done", f"Default branch set to '{branch_name}'")

    def _use_default_source(self):
        config = load_config()
        if config.default_branch:
            self.merge_source_var.set(config.default_branch)
        else:
            messagebox.showwarning("Warning", "No default branch configured")

    def _do_merge(self):
        if not self.repo:
            messagebox.showerror("Error", "Not a git repository")
            return

        source = self.merge_source_var.get()
        target = self.merge_target_var.get()
        mode = self.merge_mode_var.get()
        no_ff = self.merge_noff_var.get()

        if not source or not target:
            messagebox.showwarning("Warning", "Both source and target are required")
            return

        report = merge_branch(self.repo, source, target, mode=mode, no_ff=no_ff)
        self.merge_output.insert(tk.END, f"\n{report.result.value.upper()}: {report.message}")
        if report.conflict_files:
            self.merge_output.insert(tk.END, f"\nConflicts: {', '.join(report.conflict_files)}")
        self.merge_output.see(tk.END)

    def _use_current_branch_for_rebase(self):
        if self.repo:
            current = get_current_branch(self.repo)
            self.rebase_branch_var.set(current)

    def _do_rebase(self):
        if not self.repo:
            messagebox.showerror("Error", "Not a git repository")
            return

        branch = self.rebase_branch_var.get() or None
        upstream = self.rebase_upstream_var.get()
        mode = self.rebase_mode_var.get()

        if not upstream:
            messagebox.showwarning("Warning", "Upstream branch is required")
            return

        report = rebase_branch(self.repo, upstream=upstream, branch=branch, mode=mode)
        self.rebase_output.insert(tk.END, f"\n{report.result.value.upper()}: {report.message}")
        if report.conflict_files:
            self.rebase_output.insert(tk.END, f"\nConflicts: {', '.join(report.conflict_files)}")
        self.rebase_output.see(tk.END)
        self._refresh()

    def _rebase_continue(self):
        if not self.repo:
            return
        success, msg = rebase_continue(self.repo)
        self.rebase_output.insert(tk.END, f"\n{'SUCCESS' if success else 'ERROR'}: {msg}")
        self.rebase_output.see(tk.END)
        self._refresh()

    def _rebase_skip(self):
        if not self.repo:
            return
        success, msg = rebase_skip(self.repo)
        self.rebase_output.insert(tk.END, f"\n{'SUCCESS' if success else 'ERROR'}: {msg}")
        self.rebase_output.see(tk.END)
        self._refresh()

    def _rebase_abort(self):
        if not self.repo:
            return
        success, msg = rebase_abort(self.repo)
        self.rebase_output.insert(tk.END, f"\n{'SUCCESS' if success else 'ERROR'}: {msg}")
        self.rebase_output.see(tk.END)
        self._refresh()


    def _suggest_commit_message(self):
        if self.repo:
            msg = generate_commit_message(self.repo)
            self.commit_msg_var.set(msg)

    def _commit_all(self):
        if not self.repo:
            return
        if not has_uncommitted_changes(self.repo):
            messagebox.showinfo("Info", "No changes to commit")
            return

        msg = self.commit_msg_var.get()
        success, result = commit_changes(self.repo, message=msg if msg else None)
        if success:
            self.commit_msg_var.set("")
            self._refresh_commit_history()
            messagebox.showinfo("Done", f"Committed: {result}")
        else:
            messagebox.showerror("Error", result)

    def _publish_current(self):
        if not self.repo:
            messagebox.showerror("Error", "Not a git repository")
            return
        message = self.commit_msg_var.get() or None
        result = publish_branch(self.repo, message=message)
        if result.success:
            self.commit_msg_var.set("")
            self._refresh_commit_history()
            messagebox.showinfo("Done", result.message)
        else:
            messagebox.showerror("Publish failed", result.message)

    def _cherry_pick_selected(self):
        sel = self.commit_tree.selection()
        if not sel or not self.repo:
            return

        item = self.commit_tree.item(sel[0])
        commit_hash = item["values"][0]
        target = self.cp_target_var.get()

        if not target:
            messagebox.showwarning("Warning", "Target branch required")
            return

        report = cherry_pick_commit(self.repo, commit_hash, target)
        msg = f"{report.result.value}: {report.message}"
        if report.conflict_files:
            msg += f"\nConflicts: {', '.join(report.conflict_files)}"
        if report.suggestion:
            msg += f"\n{report.suggestion}"
        messagebox.showinfo("Cherry-pick Result", msg)

    def _revert_selected(self):
        sel = self.commit_tree.selection()
        if not sel or not self.repo:
            return

        item = self.commit_tree.item(sel[0])
        commit_hash = item["values"][0]

        if messagebox.askyesno("Confirm", f"Revert commit {commit_hash}?"):
            from branchs.core.commit import revert_commit

            success, msg = revert_commit(self.repo, commit_hash)
            if success:
                self._refresh_commit_history()
                messagebox.showinfo("Done", msg)
            else:
                messagebox.showerror("Error", msg)

    def _save_remote_config_from_gui(self):
        primary = self.primary_remote_var.get().strip()
        secondary = self.secondary_remote_var.get().strip()
        if not primary or not secondary:
            messagebox.showwarning("Warning", "Both primary and secondary remotes are required")
            return
        try:
            set_remote_config(primary, secondary)
            messagebox.showinfo("Done", f"Remote config saved: primary={primary}, secondary={secondary}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _do_sync(self):
        if not self.repo:
            messagebox.showerror("Error", "Not a git repository")
            return

        primary = self.primary_remote_var.get().strip()
        secondary = self.secondary_remote_var.get().strip()

        if not primary or not secondary:
            messagebox.showwarning("Warning", "Both primary and secondary remotes are required")
            return

        self.remote_output.insert(tk.END, "\nSyncing... Please wait...\n")
        self.remote_output.update()

        report = sync_remotes(self.repo, primary, secondary)
        self.remote_output.insert(tk.END, report.summary())


    def _save_config(self):
        config = load_config()
        config.default_branch = self.default_branch_var.get() or None
        config.default_merge_mode = self.config_mode_var.get()
        save_config(config)
        messagebox.showinfo("Done", "Configuration saved")

    def _open_repo(self):
        from tkinter import filedialog

        path = filedialog.askdirectory(title="Select Git Repository")
        if path:
            try:
                self.repo = git.Repo(path)
                self._refresh()
            except Exception as e:
                messagebox.showerror("Error", f"Invalid git repository: {e}")


def main():
    root = tk.Tk()
    app = BranchManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
