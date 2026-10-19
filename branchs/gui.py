import queue
import threading
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
    get_staged_paths,
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
    remember_repo,
)
from branchs.core.git import (
    get_current_branch,
    list_branches,
    list_remotes,
    get_remotes_info,
    fetch_all,
    rebase_abort,
    rebase_continue,
    rebase_skip,
    is_rebasing,
)
from branchs.core.remote import sync_remotes
from branchs.core.publish import get_publish_selection, publish_branch
from branchs.core.idea import commit_active_changelist
from branchs.core.network import git_network
from branchs.core.repositories import open_repository, startup_repository
from branchs.core.messages import COMMIT_TYPES, build_commit_message

MODE_OPTIONS = ["abort", "keep"]
BRANCH_TYPE_OPTIONS = [t.value for t in BranchType]


class BranchManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Branchs - Branch Manager")
        self.root.geometry("1120x820")
        self.root.minsize(900, 650)
        self._setup_style()
        self._publish_busy = False

        self._branch_combos = []
        self._remote_combos = []

        self.repo = startup_repository()

        self._create_menu()
        self._create_main_view()
        if self.repo:
            remember_repo(self.repo.working_tree_dir)
        self._refresh()

    def _setup_style(self):
        self.root.configure(background="#f3f5f9")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#ffffff", foreground="#243148")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#243148")
        style.configure("TLabelFrame", background="#ffffff", bordercolor="#dfe5ee", relief="solid")
        style.configure("TLabelFrame.Label", background="#ffffff", foreground="#34445f", font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background="#ffffff", foreground="#34445f")
        style.configure("TButton", padding=(13, 8), borderwidth=0, background="#e7ecf4", foreground="#243148")
        style.map("TButton", background=[("active", "#d8e2f0"), ("disabled", "#eff1f5")])
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#a7b9e5")])
        style.configure("TEntry", padding=7, fieldbackground="#ffffff", bordercolor="#d4dce8")
        style.configure("TCombobox", padding=7, fieldbackground="#ffffff", bordercolor="#d4dce8")
        style.configure("TNotebook", background="#f3f5f9", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 11), background="#e8edf5", foreground="#54647e")
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#1d4ed8")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#243148", rowheight=29, borderwidth=0)
        style.configure("Treeview.Heading", background="#eef2f8", foreground="#43536c", font=("Segoe UI", 10, "bold"), padding=(8, 7))
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1e3a8a")])
        style.configure("Horizontal.TProgressbar", background="#2563eb", troughcolor="#e5eaf2", borderwidth=0)

    def _style_text_outputs(self):
        for widget in (self.merge_output, self.rebase_output, self.remote_output):
            widget.configure(font=("Consolas", 10), background="#ffffff", foreground="#243148",
                             insertbackground="#243148", relief="flat", padx=12, pady=10)

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Repo", command=self._open_repo)
        self.recent_repo_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Repos", menu=self.recent_repo_menu)
        file_menu.add_command(label="Refresh", command=self._refresh)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Branchs v0.1.0"))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _create_main_view(self):
        repo_bar = ttk.Frame(self.root)
        repo_bar.pack(fill=tk.X, padx=10, pady=(8, 0))
        ttk.Label(repo_bar, text="Repository:").pack(side=tk.LEFT)
        self.repo_path_var = tk.StringVar()
        self.repo_combo = ttk.Combobox(repo_bar, textvariable=self.repo_path_var, state="readonly")
        self.repo_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.repo_combo.bind("<<ComboboxSelected>>", self._on_recent_repo_selected)
        ttk.Button(repo_bar, text="Open Repo...", command=self._open_repo).pack(side=tk.LEFT)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._create_branch_tab()
        self._create_merge_tab()
        self._create_rebase_tab()
        self._create_commit_tab()
        self._create_remote_tab()
        self._create_config_tab()
        self._style_text_outputs()

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
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Commit")
        canvas = tk.Canvas(page, background="#ffffff", highlightthickness=0)
        page_scroll = ttk.Scrollbar(page, orient=tk.VERTICAL, command=canvas.yview)
        page_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.configure(yscrollcommand=page_scroll.set)
        frame = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))

        message_frame = ttk.LabelFrame(frame, text="Commit message  ·  Conventional Commits")
        message_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 6), ipadx=10, ipady=8)
        message_frame.columnconfigure(2, weight=1)
        self.commit_type_var = tk.StringVar()
        self.commit_scope_var = tk.StringVar()
        self.commit_summary_var = tk.StringVar()
        self.commit_breaking_var = tk.BooleanVar()
        ttk.Label(message_frame, text="类型").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        ttk.Label(message_frame, text="影响范围（可选）").grid(row=0, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(message_frame, text="摘要").grid(row=0, column=2, sticky="w", padx=8, pady=5)
        ttk.Combobox(message_frame, textvariable=self.commit_type_var, values=list(COMMIT_TYPES),
                     state="readonly", width=18).grid(row=1, column=0, sticky="ew", padx=8)
        ttk.Entry(message_frame, textvariable=self.commit_scope_var, width=18).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Entry(message_frame, textvariable=self.commit_summary_var).grid(row=1, column=2, sticky="ew", padx=8)
        ttk.Label(message_frame, text="详细说明（可选）").grid(row=2, column=0, sticky="w", padx=8, pady=(10, 4))
        self.commit_body_text = tk.Text(message_frame, height=2, wrap="word", font=("Segoe UI", 10),
                                        background="#ffffff", foreground="#243148", relief="flat", padx=8, pady=6)
        self.commit_body_text.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8)
        ttk.Checkbutton(message_frame, text="不兼容变更 (!)", variable=self.commit_breaking_var).grid(
            row=4, column=0, sticky="w", padx=8, pady=6)
        self.commit_preview_var = tk.StringVar()
        ttk.Label(message_frame, textvariable=self.commit_preview_var, foreground="#2563eb").grid(
            row=4, column=1, columnspan=2, sticky="w", padx=8)
        for variable in (self.commit_type_var, self.commit_scope_var, self.commit_summary_var, self.commit_breaking_var):
            variable.trace_add("write", lambda *_: self._update_commit_preview())
        self.commit_body_text.bind("<KeyRelease>", lambda _event: self._update_commit_preview())
        self._update_commit_preview()

        mode_frame = ttk.Frame(frame)
        mode_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        ttk.Label(mode_frame, text="Commit Mode:").pack(side=tk.LEFT, padx=2)
        self.commit_mode_var = tk.StringVar(value="IDEA current changelist")
        mode_combo = ttk.Combobox(
            mode_frame, textvariable=self.commit_mode_var,
            values=("IDEA current changelist", "All staged changes"), state="readonly", width=22,
        )
        mode_combo.pack(side=tk.LEFT, padx=2)
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_pending_files())
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=5)
        ttk.Button(btn_frame, text="Suggest Summary", command=self._suggest_commit_message).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Commit", command=self._commit_all).pack(side=tk.LEFT, padx=2)
        self.publish_button = ttk.Button(btn_frame, text="Publish  ·  Sync / Commit / Push",
                                         command=self._publish_current, style="Accent.TButton")
        self.publish_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh Files", command=self._refresh_pending_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh History", command=self._refresh_commit_history).pack(side=tk.LEFT, padx=2)

        self.commit_repo_var = tk.StringVar(value="No repository open")
        ttk.Label(frame, textvariable=self.commit_repo_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=5)
        ttk.Label(frame, text="STAGED FILES FOR NEW COMMIT").grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=5
        )
        self.pending_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.pending_status_var, foreground="#64748b").grid(
            row=4, column=1, columnspan=2, sticky="e", padx=10)
        files_frame = ttk.Frame(frame)
        files_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        files_frame.columnconfigure(0, weight=1)
        self.pending_files_tree = ttk.Treeview(files_frame, columns=("change", "path"), show="headings", height=5)
        self.pending_files_tree.heading("change", text="CHANGE")
        self.pending_files_tree.heading("path", text="FILE")
        self.pending_files_tree.column("change", width=110, anchor="center", stretch=False)
        self.pending_files_tree.column("path", width=700)
        self.pending_files_tree.grid(row=0, column=0, sticky="ew")
        pending_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.pending_files_tree.yview)
        pending_scroll.grid(row=0, column=1, sticky="ns")
        self.pending_files_tree.configure(yscrollcommand=pending_scroll.set)
        self.pending_files_tree.tag_configure("added", foreground="#15803d")
        self.pending_files_tree.tag_configure("deleted", foreground="#b91c1c")
        self.pending_files_tree.tag_configure("modified", foreground="#1d4ed8")

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

        self.commit_tree.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        scrollbar.grid(row=6, column=3, sticky="ns")

        cp_frame = ttk.LabelFrame(frame, text="Cherry-pick  ·  Copy selected commit to target branch, then return here (no push)")
        cp_frame.grid(row=7, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        ttk.Label(cp_frame, text="Target:").pack(side=tk.LEFT, padx=2)
        self.cp_target_var = tk.StringVar()
        self.cp_target_combo = ttk.Combobox(cp_frame, textvariable=self.cp_target_var, width=18)
        self.cp_target_combo.pack(side=tk.LEFT, padx=2)
        self._branch_combos.append(self.cp_target_combo)
        ttk.Button(cp_frame, text="Cherry-pick Selected", command=self._cherry_pick_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(cp_frame, text="Revert Selected", command=self._revert_selected).pack(side=tk.LEFT, padx=5)

        frame.grid_rowconfigure(6, weight=1)
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

        ttk.Label(frame, text="Git network: direct connection (no proxy)").grid(
            row=2, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5
        )

    def _refresh(self):
        self._refresh_repo_selector()
        if self.repo:
            self._refresh_branch_list()
            self._refresh_remote_list()
            self._refresh_commit_history()
            self._refresh_pending_files()
            self._refresh_dropdowns()

    def _refresh_repo_selector(self):
        current = self.repo.working_tree_dir if self.repo else ""
        recent = []
        for path in load_config().recent_repos:
            try:
                resolved = open_repository(path).working_tree_dir
            except (ValueError, OSError):
                continue
            if resolved not in recent:
                recent.append(resolved)
        if current and current not in recent:
            recent.insert(0, current)
        self.repo_combo["values"] = recent
        self.repo_path_var.set(current)
        self.recent_repo_menu.delete(0, tk.END)
        if recent:
            for path in recent:
                self.recent_repo_menu.add_command(
                    label=path, command=lambda selected=path: self._switch_repo(selected)
                )
        else:
            self.recent_repo_menu.add_command(label="No recent repositories", state=tk.DISABLED)
        self.root.title(f"Branchs - {current}" if current else "Branchs - Branch Manager")

    def _on_recent_repo_selected(self, _event):
        self._switch_repo(self.repo_path_var.get())

    def _switch_repo(self, path: str):
        if self._publish_busy:
            return
        try:
            repo = open_repository(path)
            remember_repo(repo.working_tree_dir)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Error", f"Cannot open repository: {exc}")
            self._refresh_repo_selector()
            return
        self.repo = repo
        self.branch_type_var.set("")
        self.upstream_var.set("")
        self.primary_remote_var.set("")
        self.secondary_remote_var.set("")
        self._refresh()

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
            try:
                with git_network(self.repo):
                    for remote in self.repo.remotes:
                        remote.fetch()
            except git.GitCommandError as exc:
                messagebox.showerror("Fetch failed", str(exc))
                return
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
            self.commit_summary_var.set(generate_commit_message(self.repo))

    def _update_commit_preview(self):
        scope = self.commit_scope_var.get().strip()
        summary = self.commit_summary_var.get().strip() or "<填写摘要>"
        prefix = COMMIT_TYPES.get(self.commit_type_var.get(), "<选择类型>")
        self.commit_preview_var.set(
            f"预览  {prefix}{f'({scope})' if scope else ''}{'!' if self.commit_breaking_var.get() else ''}: {summary}"
        )

    def _commit_message(self):
        return build_commit_message(
            self.commit_type_var.get(), self.commit_summary_var.get(), self.commit_scope_var.get(),
            self.commit_body_text.get("1.0", "end-1c"), self.commit_breaking_var.get(),
        )

    def _clear_commit_message(self):
        self.commit_summary_var.set("")
        self.commit_scope_var.set("")
        self.commit_body_text.delete("1.0", tk.END)
        self.commit_breaking_var.set(False)

    def _refresh_pending_files(self):
        if not self.repo:
            return
        self.commit_repo_var.set(f"Repository: {self.repo.working_tree_dir}    Branch: {get_current_branch(self.repo)}")
        for item in self.pending_files_tree.get_children():
            self.pending_files_tree.delete(item)
        try:
            selection = get_publish_selection(self.repo, self._commit_mode())
            self.pending_status_var.set(f"{selection.description}  ·  {len(selection.display)} file(s)")
            for line in selection.display:
                code, _, path = line.partition("\t")
                label, tag = ({"A": ("ADDED", "added"), "D": ("DELETED", "deleted")}
                              .get(code[:1], ("MODIFIED", "modified")))
                self.pending_files_tree.insert("", tk.END, values=(label, path or code), tags=(tag,))
            if not selection.display:
                self.pending_files_tree.insert("", tk.END, values=("—", "No staged files in selected mode"))
        except ValueError as exc:
            self.pending_status_var.set("Selection needs attention")
            self.pending_files_tree.insert("", tk.END, values=("NOTICE", str(exc)))

    def _commit_mode(self):
        return "idea" if self.commit_mode_var.get() == "IDEA current changelist" else "all"

    def _commit_all(self):
        if not self.repo:
            return
        if not get_staged_paths(self.repo):
            messagebox.showinfo("Info", "No staged changes to commit; add files in IDEA or Git first")
            return

        try:
            msg = self._commit_message()
            if self._commit_mode() == "idea":
                success, result = commit_active_changelist(self.repo, message=msg)
            else:
                success, result = commit_changes(self.repo, message=msg)
        except ValueError as exc:
            messagebox.showerror("Commit failed", str(exc))
            return
        self._refresh_pending_files()
        if success:
            self._clear_commit_message()
            self._refresh_commit_history()
            messagebox.showinfo("Done", f"Committed: {result}")
        else:
            messagebox.showerror("Error", result)

    def _publish_current(self):
        if self._publish_busy:
            return
        if not self.repo:
            messagebox.showerror("Error", "Not a git repository")
            return
        mode = self._commit_mode()
        try:
            selection = get_publish_selection(self.repo, mode)
            message = self._commit_message() if selection.paths else None
        except ValueError as exc:
            messagebox.showerror("Publish failed", str(exc))
            return
        summary = "\n".join(selection.display[:12]) or "No new commit; existing local commits may still be pushed."
        if len(selection.display) > 12:
            summary += f"\n... and {len(selection.display) - 12} more (see file list in Commit tab)"
        if not messagebox.askyesno(
            "Confirm publish",
            f"Repository: {self.repo.working_tree_dir}\nBranch: {get_current_branch(self.repo)}\n\n"
            f"Mode: {selection.description}\nFiles for the new commit:\n{summary}\n\nSync, rebase, commit and push?",
        ):
            return
        self._start_publish(message, mode)

    def _start_publish(self, message, mode):
        self._publish_busy = True
        self.publish_button.configure(state="disabled")
        dialog = tk.Toplevel(self.root)
        dialog.title("Publishing branch")
        dialog.geometry("540x190")
        dialog.resizable(False, False)
        dialog.configure(background="#ffffff")
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(dialog, text="Publishing branch", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=24, pady=(22, 8))
        stage_var = tk.StringVar(value="Starting…")
        ttk.Label(dialog, textvariable=stage_var).pack(anchor="w", padx=24, pady=(0, 12))
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=480)
        progress.pack(fill="x", padx=24)
        progress.start(12)
        ttk.Label(dialog, text="Network steps may take some time. Current step is shown above.",
                  foreground="#64748b").pack(anchor="w", padx=24, pady=14)
        dialog.grab_set()
        events = queue.Queue()
        repo = self.repo

        def worker():
            try:
                result = publish_branch(repo, message=message, mode=mode,
                                        progress=lambda stage: events.put(("stage", stage)))
                events.put(("result", result))
            except Exception as exc:
                events.put(("error", str(exc)))

        def poll():
            finished = None
            while True:
                try:
                    kind, value = events.get_nowait()
                except queue.Empty:
                    break
                if kind == "stage":
                    stage_var.set(value)
                else:
                    finished = (kind, value)
            if finished is None:
                dialog.after(100, poll)
                return
            progress.stop()
            dialog.grab_release()
            dialog.destroy()
            self._publish_busy = False
            self.publish_button.configure(state="normal")
            self._refresh_pending_files()
            self._refresh_commit_history()
            kind, value = finished
            if kind == "error":
                messagebox.showerror("Publish failed", value)
            elif value.success:
                if message:
                    self._clear_commit_message()
                messagebox.showinfo("Done", value.message)
            else:
                messagebox.showerror("Publish failed", value.message)

        threading.Thread(target=worker, daemon=True).start()
        dialog.after(100, poll)

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

        try:
            report = sync_remotes(self.repo, primary, secondary)
        except git.GitCommandError as exc:
            messagebox.showerror("Sync failed", str(exc))
            return
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
            self._switch_repo(path)


def main():
    root = tk.Tk()
    app = BranchManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
