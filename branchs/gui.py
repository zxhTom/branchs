import queue
import re
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
    set_gui_theme,
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
from branchs.core.idea import commit_active_changelist, get_active_changelist, stage_idea_changes
from branchs.core.network import git_network
from branchs.core.repositories import open_repository, startup_repository
from branchs.core.messages import COMMIT_TYPES, build_commit_message, suggest_scopes
from branchs.gui_theme import palette

MODE_OPTIONS = ["abort", "keep"]
BRANCH_TYPE_OPTIONS = [t.value for t in BranchType]


class BranchManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Branchs - Branch Manager")
        self.root.geometry("1120x820")
        self.root.minsize(900, 650)
        self.theme = load_config().gui_theme
        self._setup_style()
        self._publish_busy = False
        self._reference_popup = None

        self._branch_combos = []
        self._remote_combos = []

        self.repo = startup_repository()

        self._create_menu()
        self._create_main_view()
        self._apply_theme()
        if self.repo:
            remember_repo(self.repo.working_tree_dir)
        self._refresh()

    def _setup_style(self):
        p = palette(self.theme)
        self.root.configure(background=p["window"])
        style = ttk.Style(self.root)
        if style.theme_use() != "clam":
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=p["surface"], foreground=p["text"])
        style.configure("TFrame", background=p["surface"])
        style.configure("TLabel", background=p["surface"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("Section.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI", 12, "bold"))
        style.configure("Accent.TLabel", background=p["surface"], foreground=p["modified"])
        style.configure("TLabelFrame", background=p["surface"], bordercolor=p["border"], relief="solid")
        style.configure("TLabelFrame.Label", background=p["surface"], foreground=p["text"], font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background=p["surface"], foreground=p["text"])
        style.map("TCheckbutton", background=[("active", p["surface"])], foreground=[("disabled", p["muted"])])
        style.configure("TButton", padding=(12, 8), borderwidth=1, bordercolor=p["border"],
                        background=p["button"], foreground=p["button_text"])
        style.map("TButton", background=[("active", p["button_hover"]), ("disabled", p["button"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("Accent.TButton", padding=(14, 9), borderwidth=0, background=p["accent"],
                        foreground=p["accent_text"], font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", p["accent_hover"]), ("disabled", p["button"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("Compact.TButton", padding=(7, 4), borderwidth=0,
                        background=p["button"], foreground=p["button_text"])
        style.map("Compact.TButton", background=[("active", p["button_hover"])])
        style.configure("Header.TButton", padding=(10, 7), borderwidth=0,
                        background=p["button"], foreground=p["button_text"])
        style.map("Header.TButton", background=[("active", p["button_hover"])])
        for name in ("TEntry", "TCombobox"):
            style.configure(name, padding=7, fieldbackground=p["input"], foreground=p["text"],
                            bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"],
                            insertcolor=p["text"], arrowcolor=p["text"])
            style.map(name, fieldbackground=[("readonly", p["input"]), ("disabled", p["button"])],
                      foreground=[("readonly", p["text"]), ("disabled", p["muted"])],
                      selectbackground=[("readonly", p["input"])], selectforeground=[("readonly", p["text"])])
        style.configure("Flat.TNotebook", background=p["surface"], borderwidth=0,
                        bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"])
        style.layout("Flat.TNotebook.Tab", [])
        style.configure("Treeview", background=p["tree"], fieldbackground=p["tree"],
                        foreground=p["text"], rowheight=32, borderwidth=0,
                        bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"])
        style.configure("Treeview.Heading", background=p["heading"], foreground=p["muted"],
                        font=("Segoe UI", 9, "bold"), padding=(9, 8), relief="flat")
        style.map("Treeview", background=[("selected", p["selected"])],
                  foreground=[("selected", p["selected_text"])])
        style.map("Treeview.Heading", background=[("active", p["button_hover"])])
        style.configure("TScrollbar", background=p["button"], troughcolor=p["surface"],
                        arrowcolor=p["muted"], bordercolor=p["border"], lightcolor=p["button"], darkcolor=p["button"])
        style.map("TScrollbar", background=[("active", p["button_hover"])])
        style.configure("TSeparator", background=p["border"])
        style.configure("Horizontal.TProgressbar", background=p["accent"], troughcolor=p["heading"], borderwidth=0)
        self.root.option_add("*TCombobox*Listbox.background", p["input"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["selected"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["selected_text"])

    def _style_text_outputs(self):
        p = palette(self.theme)
        for widget in (self.merge_output, self.rebase_output, self.remote_output):
            widget.configure(font=("Consolas", 10), background=p["input"], foreground=p["text"],
                             insertbackground=p["text"], selectbackground=p["selected"],
                             selectforeground=p["selected_text"], relief="flat", padx=12, pady=10,
                             borderwidth=0, highlightthickness=1, highlightbackground=p["border"],
                             highlightcolor=p["accent"])
            widget.vbar.configure(background=p["button"], troughcolor=p["surface"],
                                  activebackground=p["button_hover"])

    def _apply_theme(self):
        self._setup_style()
        p = palette(self.theme)
        self.header.configure(background=p["header"])
        self.header_brand.configure(background=p["header"], foreground=p["text"])
        self.header_caption.configure(background=p["header"], foreground=p["muted"])
        self.nav.configure(background=p["surface"], highlightbackground=p["border"])
        self.theme_button.configure(text="Dark mode" if self.theme == "light" else "Light mode")
        self.theme_var.set("Light" if self.theme == "light" else "Dark")
        self._update_nav()
        self._style_text_outputs()
        self.commit_body_text.configure(background=p["input"], foreground=p["text"],
                                        insertbackground=p["text"], selectbackground=p["selected"],
                                        selectforeground=p["selected_text"], highlightbackground=p["border"],
                                        highlightcolor=p["accent"], highlightthickness=1, borderwidth=0)
        for tag in ("added", "deleted", "modified"):
            self.pending_files_tree.tag_configure(tag, foreground=p[tag])
        for menu in (self.app_menu, self.recent_repo_menu):
            menu.configure(background=p["surface"], foreground=p["text"],
                           activebackground=p["selected"], activeforeground=p["selected_text"])
        self._style_combo_popdowns(p)

    def _style_combo_popdowns(self, p):
        def visit(widget):
            if isinstance(widget, ttk.Combobox):
                try:
                    popdown = widget.tk.call("ttk::combobox::PopdownWindow", str(widget))
                    widget.tk.call(f"{popdown}.f.l", "configure", "-background", p["input"],
                                   "-foreground", p["text"], "-selectbackground", p["selected"],
                                   "-selectforeground", p["selected_text"])
                except tk.TclError:
                    pass
            for child in widget.winfo_children():
                visit(child)
        visit(self.root)

    def _set_theme(self, theme):
        if theme == self.theme:
            return
        set_gui_theme(theme)
        self.theme = theme
        self._apply_theme()

    def _toggle_theme(self):
        self._set_theme("dark" if self.theme == "light" else "light")

    def _on_theme_selected(self, _event):
        self._set_theme("dark" if self.theme_var.get() == "Dark" else "light")

    def _create_menu(self):
        self.app_menu = tk.Menu(self.root, tearoff=0)
        self.app_menu.add_command(label="Open repository", command=self._open_repo)
        self.recent_repo_menu = tk.Menu(self.app_menu, tearoff=0)
        self.app_menu.add_cascade(label="Recent repositories", menu=self.recent_repo_menu)
        self.app_menu.add_command(label="Refresh", command=self._refresh)
        self.app_menu.add_separator()
        self.app_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Branchs v0.1.0"))
        self.app_menu.add_command(label="Exit", command=self.root.quit)

    def _show_app_menu(self):
        x = self.menu_button.winfo_rootx()
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height()
        try:
            self.app_menu.tk_popup(x, y)
        finally:
            self.app_menu.grab_release()

    def _create_main_view(self):
        p = palette(self.theme)
        self.header = tk.Frame(self.root, background=p["header"], height=78)
        self.header.pack(fill=tk.X)
        self.header.pack_propagate(False)
        self.header_brand = tk.Label(self.header, text="branchs", background=p["header"], foreground=p["text"],
                                     font=("Segoe UI", 18, "bold"))
        self.header_brand.pack(side=tk.LEFT, padx=(24, 28))
        self.header_caption = tk.Label(self.header, text="REPOSITORY", background=p["header"], foreground=p["muted"],
                                       font=("Segoe UI", 9, "bold"))
        self.header_caption.pack(side=tk.LEFT, padx=(0, 10))
        self.repo_path_var = tk.StringVar()
        self.repo_combo = ttk.Combobox(self.header, textvariable=self.repo_path_var, state="readonly")
        self.repo_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.repo_combo.bind("<<ComboboxSelected>>", self._on_recent_repo_selected)
        ttk.Button(self.header, text="Open", command=self._open_repo,
                   style="Header.TButton").pack(side=tk.LEFT, padx=(10, 6))
        self.theme_button = ttk.Button(self.header, command=self._toggle_theme, style="Header.TButton")
        self.theme_button.pack(side=tk.LEFT, padx=(0, 6))
        self.menu_button = ttk.Button(self.header, text="Menu", command=self._show_app_menu,
                                      style="Header.TButton")
        self.menu_button.pack(side=tk.LEFT, padx=(0, 24))

        self.nav = tk.Frame(self.root, background=p["surface"], height=52,
                            highlightbackground=p["border"], highlightthickness=1)
        self.nav.pack(fill=tk.X)
        self.nav.pack_propagate(False)
        self._nav_buttons = []
        for index, label in enumerate(("Branches", "Merge", "Rebase", "Commit", "Remote Sync", "Settings")):
            button = tk.Button(self.nav, text=label, command=lambda i=index: self.notebook.select(i),
                               background=p["surface"], foreground=p["muted"], activebackground=p["selected"],
                               activeforeground=p["selected_text"], relief="flat", borderwidth=0,
                               highlightthickness=0, font=("Segoe UI", 10), padx=17, pady=12, cursor="hand2")
            button.pack(side=tk.LEFT, padx=(9 if index == 0 else 0, 0))
            self._nav_buttons.append(button)

        self.notebook = ttk.Notebook(self.root, style="Flat.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._create_branch_tab()
        self._create_merge_tab()
        self._create_rebase_tab()
        self._create_commit_tab()
        self._create_remote_tab()
        self._create_config_tab()
        self._style_text_outputs()
        self.notebook.bind("<<NotebookTabChanged>>", self._update_nav)
        self._update_nav()

    def _update_nav(self, _event=None):
        p = palette(self.theme)
        active = self.notebook.index(self.notebook.select())
        for index, button in enumerate(self._nav_buttons):
            selected = index == active
            button.configure(foreground=p["selected_text"] if selected else p["muted"],
                             background=p["selected"] if selected else p["surface"],
                             activebackground=p["selected"], activeforeground=p["selected_text"],
                             font=("Segoe UI", 10, "bold" if selected else "normal"))

    def _create_branch_tab(self):
        frame = ttk.Frame(self.notebook, padding=(18, 16))
        self.notebook.add(frame, text="Branches")

        ttk.Label(frame, text="Branches", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(frame, text="Review local branches and set their type and upstream.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Refresh", command=self._refresh_branch_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Fetch All", command=self._fetch_all).pack(side=tk.LEFT, padx=2)

        tree_area = ttk.Frame(frame)
        tree_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        columns = ("name", "type", "upstream", "current")
        self.branch_tree = ttk.Treeview(tree_area, columns=columns, show="headings")
        self.branch_tree.heading("name", text="Branch")
        self.branch_tree.heading("type", text="Type")
        self.branch_tree.heading("upstream", text="Upstream")
        self.branch_tree.heading("current", text="Current")

        self.branch_tree.column("name", width=200)
        self.branch_tree.column("type", width=100)
        self.branch_tree.column("upstream", width=200)
        self.branch_tree.column("current", width=60)

        scrollbar = ttk.Scrollbar(tree_area, orient=tk.VERTICAL, command=self.branch_tree.yview)
        self.branch_tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.branch_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Merge")
        left, right = self._operation_columns(page)
        ttk.Label(left, text="Merge branches", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(left, text="Bring changes from a source branch into a target branch.",
                  style="Muted.TLabel", wraplength=350).pack(anchor="w", pady=(0, 22))

        ttk.Label(left, text="Source branch").pack(anchor="w", pady=(0, 5))
        source_row = ttk.Frame(left)
        source_row.pack(fill=tk.X, pady=(0, 16))
        self.merge_source_var = tk.StringVar()
        self.merge_source_combo = ttk.Combobox(source_row, textvariable=self.merge_source_var)
        self.merge_source_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._branch_combos.append(self.merge_source_combo)
        ttk.Button(source_row, text="Default", command=self._use_default_source,
                   style="Compact.TButton").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(left, text="Target branch").pack(anchor="w", pady=(0, 5))
        self.merge_target_var = tk.StringVar()
        self.merge_target_combo = ttk.Combobox(left, textvariable=self.merge_target_var)
        self.merge_target_combo.pack(fill=tk.X, pady=(0, 16))
        self._branch_combos.append(self.merge_target_combo)

        ttk.Label(left, text="Conflict handling").pack(anchor="w", pady=(0, 5))
        self.merge_mode_var = tk.StringVar(value="abort")
        ttk.Combobox(left, textvariable=self.merge_mode_var, values=MODE_OPTIONS,
                     state="readonly").pack(fill=tk.X, pady=(0, 14))
        self.merge_noff_var = tk.BooleanVar()
        ttk.Checkbutton(left, text="Create a merge commit (no fast-forward)",
                        variable=self.merge_noff_var).pack(anchor="w", pady=(0, 20))
        ttk.Button(left, text="Merge branches", command=self._do_merge,
                   style="Accent.TButton").pack(fill=tk.X)

        ttk.Label(right, text="Activity", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(right, text="Merge results and conflict details appear here.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.merge_output = scrolledtext.ScrolledText(right, wrap="word")
        self.merge_output.pack(fill=tk.BOTH, expand=True)

    def _create_rebase_tab(self):
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Rebase")
        left, right = self._operation_columns(page)
        ttk.Label(left, text="Rebase branch", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(left, text="Replay a branch on top of its upstream branch.",
                  style="Muted.TLabel", wraplength=350).pack(anchor="w", pady=(0, 22))

        ttk.Label(left, text="Branch to rebase").pack(anchor="w", pady=(0, 5))
        branch_row = ttk.Frame(left)
        branch_row.pack(fill=tk.X, pady=(0, 16))
        self.rebase_branch_var = tk.StringVar()
        self.rebase_branch_combo = ttk.Combobox(branch_row, textvariable=self.rebase_branch_var)
        self.rebase_branch_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._branch_combos.append(self.rebase_branch_combo)
        ttk.Button(branch_row, text="Current", command=self._use_current_branch_for_rebase,
                   style="Compact.TButton").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(left, text="Rebase onto").pack(anchor="w", pady=(0, 5))
        self.rebase_upstream_var = tk.StringVar()
        self.rebase_upstream_combo = ttk.Combobox(left, textvariable=self.rebase_upstream_var)
        self.rebase_upstream_combo.pack(fill=tk.X, pady=(0, 16))
        self._branch_combos.append(self.rebase_upstream_combo)

        ttk.Label(left, text="Conflict handling").pack(anchor="w", pady=(0, 5))
        self.rebase_mode_var = tk.StringVar(value="abort")
        ttk.Combobox(left, textvariable=self.rebase_mode_var, values=MODE_OPTIONS,
                     state="readonly").pack(fill=tk.X, pady=(0, 20))
        ttk.Button(left, text="Start rebase", command=self._do_rebase,
                   style="Accent.TButton").pack(fill=tk.X, pady=(0, 18))
        ttk.Separator(left).pack(fill=tk.X, pady=(0, 12))
        ttk.Label(left, text="In-progress rebase", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        continuation = ttk.Frame(left)
        continuation.pack(fill=tk.X)
        for caption, action in (("Continue", self._rebase_continue),
                                ("Skip", self._rebase_skip), ("Abort", self._rebase_abort)):
            ttk.Button(continuation, text=caption, command=action).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ttk.Label(right, text="Activity", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(right, text="Rebase results and conflict details appear here.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.rebase_output = scrolledtext.ScrolledText(right, wrap="word")
        self.rebase_output.pack(fill=tk.BOTH, expand=True)

    def _operation_columns(self, page):
        page.columnconfigure(0, weight=2, uniform="operation_panes")
        page.columnconfigure(1, weight=3, uniform="operation_panes")
        page.rowconfigure(0, weight=1)
        left = ttk.Frame(page, padding=(22, 22))
        left.grid(row=0, column=0, sticky="nsew")
        ttk.Separator(page, orient=tk.VERTICAL).grid(row=0, column=0, sticky="nse")
        right = ttk.Frame(page, padding=(22, 22))
        right.grid(row=0, column=1, sticky="nsew")
        return left, right

    def _create_commit_tab(self):
        p = palette(self.theme)
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Commit")
        page.columnconfigure(0, weight=2, uniform="commit_panes")
        page.columnconfigure(1, weight=3, uniform="commit_panes")
        page.rowconfigure(0, weight=1)

        left = ttk.Frame(page, padding=(18, 16))
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        ttk.Separator(page, orient=tk.VERTICAL).grid(row=0, column=0, sticky="nse")
        right = ttk.Frame(page, padding=(20, 16))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        files_header = ttk.Frame(left)
        files_header.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(files_header, text="Changes", style="Section.TLabel").pack(side=tk.LEFT)
        self.pending_status_var = tk.StringVar()
        ttk.Label(files_header, textvariable=self.pending_status_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        mode_row = ttk.Frame(left)
        mode_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(mode_row, text="Commit from").pack(side=tk.LEFT, padx=(0, 8))
        self.commit_mode_var = tk.StringVar(value="IDEA current changelist")
        mode_combo = ttk.Combobox(
            mode_row, textvariable=self.commit_mode_var,
            values=("IDEA current changelist", "Add mode · Git staged"), state="readonly", width=24,
        )
        mode_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_pending_files())
        ttk.Button(mode_row, text="↻", width=3, command=self._refresh_pending_files,
                   style="Compact.TButton").pack(side=tk.LEFT, padx=(8, 0))

        files_area = ttk.Frame(left)
        files_area.grid(row=2, column=0, sticky="nsew")
        files_area.columnconfigure(0, weight=1)
        files_area.rowconfigure(0, weight=1)
        self.pending_files_tree = ttk.Treeview(files_area, columns=("change", "path"), show="headings", height=8)
        self.pending_files_tree.heading("change", text="STATUS")
        self.pending_files_tree.heading("path", text="STAGED FILE")
        self.pending_files_tree.column("change", width=88, anchor="center", stretch=False)
        self.pending_files_tree.column("path", width=280)
        self.pending_files_tree.grid(row=0, column=0, sticky="nsew")
        pending_scroll = ttk.Scrollbar(files_area, orient=tk.VERTICAL, command=self.pending_files_tree.yview)
        pending_scroll.grid(row=0, column=1, sticky="ns")
        self.pending_files_tree.configure(yscrollcommand=pending_scroll.set)
        self.pending_files_tree.tag_configure("added", foreground=p["added"])
        self.pending_files_tree.tag_configure("deleted", foreground=p["deleted"])
        self.pending_files_tree.tag_configure("modified", foreground=p["modified"])
        self.pending_hint_var = tk.StringVar(value="Only files already staged in Git can be committed.")
        ttk.Label(left, textvariable=self.pending_hint_var, style="Muted.TLabel", wraplength=390).grid(
            row=3, column=0, sticky="w", pady=(6, 8))
        ttk.Separator(left).grid(row=4, column=0, sticky="ew", pady=(0, 9))

        message_header = ttk.Frame(left)
        message_header.grid(row=5, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(message_header, text="Commit message", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(message_header, text="Suggest summary", command=self._suggest_commit_message,
                   style="Compact.TButton").pack(side=tk.RIGHT)
        self.commit_type_var = tk.StringVar()
        self.commit_scope_var = tk.StringVar()
        self.commit_summary_var = tk.StringVar()
        self.commit_breaking_var = tk.BooleanVar()
        fields = ttk.Frame(left)
        fields.grid(row=6, column=0, sticky="ew")
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text="Type").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(fields, text="Scope  ·  optional").grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 4))
        ttk.Combobox(fields, textvariable=self.commit_type_var, values=list(COMMIT_TYPES),
                     state="readonly").grid(row=1, column=0, sticky="ew")
        self.commit_scope_combo = ttk.Combobox(fields, textvariable=self.commit_scope_var)
        self.commit_scope_combo.grid(row=1, column=1, sticky="ew", padx=(10, 0))
        ttk.Label(fields, text="Summary").grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 3))
        ttk.Entry(fields, textvariable=self.commit_summary_var).grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(fields, text="Description  ·  optional").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(7, 3))
        self.commit_body_text = tk.Text(fields, height=2, wrap="word", font=("Segoe UI", 10),
                                        background=p["input"], foreground=p["text"], relief="flat",
                                        borderwidth=0, highlightthickness=1, padx=8, pady=6)
        self.commit_body_text.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(fields, text="Breaking change", variable=self.commit_breaking_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(5, 2))
        self.commit_preview_var = tk.StringVar()
        ttk.Label(fields, textvariable=self.commit_preview_var, style="Accent.TLabel",
                  wraplength=370).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 5))
        for variable in (self.commit_type_var, self.commit_scope_var, self.commit_summary_var, self.commit_breaking_var):
            variable.trace_add("write", lambda *_: self._update_commit_preview())
        self.commit_body_text.bind("<KeyRelease>", lambda _event: self._update_commit_preview())
        self.commit_body_text.bind("<KeyRelease>", self._on_description_keyrelease, add="+")
        self.commit_body_text.bind("<Down>", self._focus_reference_popup, add="+")
        self.commit_body_text.bind("<Escape>", self._hide_reference_popup, add="+")
        self._update_commit_preview()

        actions = ttk.Frame(left)
        actions.grid(row=7, column=0, sticky="ew")
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Commit", command=self._commit_all).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.publish_button = ttk.Button(actions, text="Publish",
                                         command=self._publish_current, style="Accent.TButton")
        self.publish_button.grid(row=0, column=1, sticky="ew")
        ttk.Label(left, text="Publish: sync → rebase → commit → push",
                  style="Muted.TLabel").grid(row=8, column=0, sticky="w", pady=(7, 0))

        history_header = ttk.Frame(right)
        history_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(history_header, text="History", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(history_header, text="Refresh", command=self._refresh_commit_history).pack(side=tk.RIGHT)
        ttk.Button(history_header, text="Reference selected", command=self._reference_selected_commits,
                   style="Compact.TButton").pack(side=tk.RIGHT, padx=(0, 8))
        self.commit_repo_var = tk.StringVar(value="No repository open")
        ttk.Label(right, textvariable=self.commit_repo_var, style="Muted.TLabel",
                  wraplength=600).grid(row=1, column=0, sticky="w", pady=(0, 12))
        history_area = ttk.Frame(right)
        history_area.grid(row=2, column=0, sticky="nsew")
        history_area.columnconfigure(0, weight=1)
        history_area.rowconfigure(0, weight=1)
        columns = ("hash", "author", "date", "message")
        self.commit_tree = ttk.Treeview(history_area, columns=columns, show="headings", height=12)
        for key, label in (("hash", "HASH"), ("author", "AUTHOR"), ("date", "DATE"), ("message", "MESSAGE")):
            self.commit_tree.heading(key, text=label)
        self.commit_tree.column("hash", width=82, stretch=False)
        self.commit_tree.column("author", width=100, stretch=False)
        self.commit_tree.column("date", width=95, stretch=False)
        self.commit_tree.column("message", width=290)
        self.commit_tree.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(history_area, orient=tk.VERTICAL, command=self.commit_tree.yview)
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.commit_tree.configure(yscrollcommand=history_scroll.set)
        self.commit_tree.bind("<Double-Button-1>", self._reference_history_double_click)
        self.commit_tree.bind("<Button-3>", self._show_history_context_menu)

        ttk.Separator(right).grid(row=3, column=0, sticky="ew", pady=16)
        ttk.Label(right, text="Cherry-pick", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 5))
        ttk.Label(right, text="Copy the selected commit to a local target branch. You return here afterward; no push is made.",
                  style="Muted.TLabel", wraplength=600).grid(row=5, column=0, sticky="w", pady=(0, 10))
        cherry_actions = ttk.Frame(right)
        cherry_actions.grid(row=6, column=0, sticky="ew")
        ttk.Label(cherry_actions, text="Target branch").pack(side=tk.LEFT, padx=(0, 8))
        self.cp_target_var = tk.StringVar()
        self.cp_target_combo = ttk.Combobox(cherry_actions, textvariable=self.cp_target_var, width=17)
        self.cp_target_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._branch_combos.append(self.cp_target_combo)
        ttk.Button(cherry_actions, text="Cherry-pick", command=self._cherry_pick_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(cherry_actions, text="Revert selected", command=self._revert_selected).pack(side=tk.LEFT)

    def _create_remote_tab(self):
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Remote Sync")
        left, right = self._operation_columns(page)
        ttk.Label(left, text="Remote sync", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(left, text="Review remotes and choose where to synchronize branches.",
                  style="Muted.TLabel", wraplength=350).pack(anchor="w", pady=(0, 16))
        remote_header = ttk.Frame(left)
        remote_header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(remote_header, text="Configured remotes").pack(side=tk.LEFT)
        ttk.Button(remote_header, text="Refresh", command=self._refresh_remote_list,
                   style="Compact.TButton").pack(side=tk.RIGHT)
        remote_area = ttk.Frame(left)
        remote_area.pack(fill=tk.X, pady=(0, 16))
        remote_area.columnconfigure(0, weight=1)
        self.remote_tree = ttk.Treeview(remote_area, columns=("name", "url"), show="headings", height=5)
        self.remote_tree.heading("name", text="NAME")
        self.remote_tree.heading("url", text="URL")
        self.remote_tree.column("name", width=100, stretch=False)
        self.remote_tree.column("url", width=270)
        self.remote_tree.grid(row=0, column=0, sticky="ew")
        remote_scroll = ttk.Scrollbar(remote_area, orient=tk.VERTICAL, command=self.remote_tree.yview)
        remote_scroll.grid(row=0, column=1, sticky="ns")
        self.remote_tree.configure(yscrollcommand=remote_scroll.set)
        ttk.Separator(left).pack(fill=tk.X, pady=(0, 16))
        ttk.Label(left, text="Sync settings", style="Section.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(left, text="Primary remote").pack(anchor="w", pady=(0, 5))
        self.primary_remote_var = tk.StringVar(value="origin")
        self.primary_remote_combo = ttk.Combobox(left, textvariable=self.primary_remote_var)
        self.primary_remote_combo.pack(fill=tk.X, pady=(0, 14))
        self._remote_combos.append(self.primary_remote_combo)
        ttk.Label(left, text="Secondary remote").pack(anchor="w", pady=(0, 5))
        self.secondary_remote_var = tk.StringVar(value="upstream")
        self.secondary_remote_combo = ttk.Combobox(left, textvariable=self.secondary_remote_var)
        self.secondary_remote_combo.pack(fill=tk.X, pady=(0, 16))
        self._remote_combos.append(self.secondary_remote_combo)
        sync_buttons = ttk.Frame(left)
        sync_buttons.pack(fill=tk.X)
        ttk.Button(sync_buttons, text="Save settings", command=self._save_remote_config_from_gui).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(sync_buttons, text="Sync remotes", command=self._do_sync,
                   style="Accent.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(right, text="Sync report", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(right, text="Remote activity and results appear here.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.remote_output = scrolledtext.ScrolledText(right, wrap="word")
        self.remote_output.pack(fill=tk.BOTH, expand=True)

    def _create_config_tab(self):
        frame = ttk.Frame(self.notebook, padding=(22, 22))
        self.notebook.add(frame, text="Config")

        ttk.Label(frame, text="Settings", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(frame, text="Set defaults for branch operations and Git networking.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 22))

        config = load_config()

        ttk.Label(frame, text="Default Branch:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.default_branch_var = tk.StringVar(value=config.default_branch or "")
        self.default_branch_combo = ttk.Combobox(frame, textvariable=self.default_branch_var, width=28)
        self.default_branch_combo.grid(row=2, column=1, padx=5)
        self._branch_combos.append(self.default_branch_combo)
        ttk.Button(frame, text="Save", command=self._save_config).grid(row=2, column=2, padx=5)

        ttk.Label(frame, text="Merge Mode:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.config_mode_var = tk.StringVar(value=config.default_merge_mode)
        ttk.Combobox(frame, textvariable=self.config_mode_var, values=MODE_OPTIONS, state="readonly").grid(
            row=3, column=1, sticky=tk.W, padx=5
        )

        ttk.Label(frame, text="Git network: direct connection (no proxy)").grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5
        )
        ttk.Label(frame, text="Appearance:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=(20, 5))
        self.theme_var = tk.StringVar(value="Light" if self.theme == "light" else "Dark")
        theme_combo = ttk.Combobox(frame, textvariable=self.theme_var, values=("Light", "Dark"),
                                   state="readonly", width=26)
        theme_combo.grid(row=5, column=1, sticky=tk.W, padx=5, pady=(20, 5))
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme_selected)
        ttk.Label(frame, text="Changes apply immediately and are remembered for next launch.",
                  style="Muted.TLabel").grid(row=6, column=1, columnspan=2, sticky=tk.W, padx=5)

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
                "", tk.END, iid=c.hash,
                values=(c.hash[:8], c.author, c.date.strftime("%Y-%m-%d"), c.message[:60])
            )

    def _reference_selected_commits(self):
        selected = self.commit_tree.selection()
        if not selected:
            messagebox.showinfo("Select a commit", "Select one or more commits in History first")
            return
        self._hide_reference_popup()
        body = self.commit_body_text.get("1.0", "end-1c")
        existing = set(body.splitlines())
        references = [f"@commit {commit_id}" for commit_id in selected
                      if f"@commit {commit_id}" not in existing]
        if references:
            separator = "\n" if body and not body.endswith("\n") else ""
            self.commit_body_text.insert(tk.END, separator + "\n".join(references))
            self.commit_body_text.focus_set()

    def _reference_history_double_click(self, event):
        commit_id = self.commit_tree.identify_row(event.y)
        if commit_id:
            self._insert_commit_reference(commit_id)

    def _show_history_context_menu(self, event):
        commit_id = self.commit_tree.identify_row(event.y)
        if not commit_id:
            return
        self.commit_tree.selection_set(commit_id)
        menu = tk.Menu(self.commit_tree, tearoff=0)
        p = palette(self.theme)
        menu.configure(background=p["surface"], foreground=p["text"],
                       activebackground=p["selected"], activeforeground=p["selected_text"])
        menu.add_command(label="Reference in Description", command=lambda: self._insert_commit_reference(commit_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _insert_commit_reference(self, commit_id, replace_match=False):
        self._hide_reference_popup()
        body = self.commit_body_text
        reference = f"@commit {commit_id}"
        if replace_match:
            before = body.get("1.0", "insert")
            match = re.search(r"@([^\s@]*)$", before)
            if match:
                body.delete(f"insert-{len(match.group(0))}c", "insert")
        elif body.get("1.0", "end-1c") and body.compare("insert", "==", "end-1c"):
            if not body.get("end-2c", "end-1c") == "\n":
                body.insert("insert", "\n")
        body.insert("insert", reference)
        body.focus_set()

    def _on_description_keyrelease(self, _event):
        before = self.commit_body_text.get("1.0", "insert")
        match = re.search(r"@([^\s@]*)$", before)
        if not match or not self.repo:
            self._hide_reference_popup()
            return
        query = match.group(1).casefold()
        if query == "commit":
            query = ""
        commits = get_commit_history(self.repo, max_count=50)
        matches = [c for c in commits if query in c.hash.casefold() or query in c.message.casefold()]
        if not matches:
            self._hide_reference_popup()
            return
        self._hide_reference_popup()
        p = palette(self.theme)
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(background=p["border"])
        popup.geometry(
            f"{max(360, self.commit_body_text.winfo_width())}x{min(8, len(matches)) * 27 + 8}"
            f"+{self.commit_body_text.winfo_rootx()}"
            f"+{self.commit_body_text.winfo_rooty() + self.commit_body_text.winfo_height()}"
        )
        choices = tk.Listbox(popup, background=p["input"], foreground=p["text"],
                             selectbackground=p["selected"], selectforeground=p["selected_text"],
                             font=("Segoe UI", 10), relief="flat", borderwidth=1,
                             highlightthickness=0, activestyle="none")
        choices.pack(fill="both", expand=True, padx=1, pady=1)
        self._reference_popup = popup
        self._reference_choices = choices
        self._reference_hashes = [c.hash for c in matches[:8]]
        for commit in matches[:8]:
            choices.insert(tk.END, f"{commit.hash[:10]}  {commit.message}")
        choices.bind("<ButtonRelease-1>", self._choose_reference_popup)
        choices.bind("<Return>", self._choose_reference_popup)
        choices.bind("<Escape>", self._hide_reference_popup)
        popup.lift()

    def _focus_reference_popup(self, _event):
        if not self._reference_popup:
            return None
        self._reference_choices.selection_clear(0, tk.END)
        self._reference_choices.selection_set(0)
        self._reference_choices.focus_set()
        return "break"

    def _choose_reference_popup(self, _event):
        selected = self._reference_choices.curselection()
        if selected:
            self._insert_commit_reference(self._reference_hashes[selected[0]], replace_match=True)
        return "break"

    def _hide_reference_popup(self, _event=None):
        if self._reference_popup:
            self._reference_popup.destroy()
            self._reference_popup = None
        return "break" if _event and getattr(_event, "keysym", None) == "Escape" else None


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
        self.commit_scope_combo["values"] = suggest_scopes(self.repo)
        for item in self.pending_files_tree.get_children():
            self.pending_files_tree.delete(item)
        try:
            if self._commit_mode() == "idea":
                selection = get_active_changelist(self.repo)
                ready = set(selection.paths)
                self.pending_files_tree.heading("path", text="IDEA CHANGE")
                self.pending_status_var.set(
                    f"{selection.name} · {len(selection.visible_paths)} file(s) · {len(ready)} staged"
                )
                for path in selection.visible_paths:
                    is_staged = path in ready
                    self.pending_files_tree.insert("", tk.END,
                                                   values=("STAGED" if is_staged else "ADD FIRST", path),
                                                   tags=("added" if is_staged else "deleted",))
                if not selection.visible_paths:
                    self.pending_files_tree.insert("", tk.END, values=("—", "No tracked changes in active IDEA changelist"))
                outside = sorted(set(get_staged_paths(self.repo)) - ready)
                if outside:
                    self.pending_hint_var.set(
                        "Staged files outside this changelist block IDEA mode; unstage them or use Add mode."
                    )
                else:
                    self.pending_hint_var.set(
                        "IDEA Changes may be unstaged. Only rows marked STAGED can enter the commit."
                    )
            else:
                selection = get_publish_selection(self.repo, "add")
                self.pending_files_tree.heading("path", text="STAGED FILE")
                self.pending_status_var.set(f"Git index · {len(selection.display)} file(s)")
                self.pending_hint_var.set("Add mode commits exactly the existing Git index; no git add is run.")
                for line in selection.display:
                    code, _, path = line.partition("\t")
                    label, tag = ({"A": ("ADDED", "added"), "D": ("DELETED", "deleted")}
                                  .get(code[:1], ("MODIFIED", "modified")))
                    self.pending_files_tree.insert("", tk.END, values=(label, path or code), tags=(tag,))
                if not selection.display:
                    self.pending_files_tree.insert("", tk.END, values=("—", "No files staged in Git"))
        except ValueError as exc:
            self.pending_status_var.set("Selection needs attention")
            self.pending_hint_var.set("Switch to Add mode to use files already staged in Git.")
            self.pending_files_tree.insert("", tk.END, values=("NOTICE", str(exc)))

    def _commit_mode(self):
        return "idea" if self.commit_mode_var.get() == "IDEA current changelist" else "add"

    def _prepare_idea_selection(self):
        selection = get_publish_selection(self.repo, "idea")
        changelist = get_active_changelist(self.repo)
        unstaged = sorted(set(changelist.visible_paths) - set(changelist.paths))
        if unstaged:
            listed = "\n".join(unstaged[:12])
            if len(unstaged) > 12:
                listed += f"\n... and {len(unstaged) - 12} more"
            answer = messagebox.askyesnocancel(
                "IDEA changes need staging",
                f"These IDEA Changes are not staged:\n{listed}\n\n"
                "Yes: stage exactly these files, then continue.\n"
                "No: continue with STAGED files only.\nCancel: stop.",
            )
            if answer is None:
                return None
            if answer:
                stage_idea_changes(self.repo, unstaged)
                selection = get_publish_selection(self.repo, "idea")
                self._refresh_pending_files()
        if not selection.paths and changelist.visible_paths:
            messagebox.showinfo("Nothing staged", "No IDEA Changes are staged. Confirm staging to continue.")
            return None
        return selection

    def _commit_all(self):
        if not self.repo:
            return
        try:
            msg = self._commit_message()
            if self._commit_mode() == "idea":
                selection = self._prepare_idea_selection()
                if selection is None:
                    return
            elif not get_staged_paths(self.repo):
                messagebox.showinfo("Info", "No staged changes to commit; add files in IDEA or Git first")
                return
            if self._commit_mode() == "idea":
                success, result = commit_active_changelist(self.repo, message=msg)
            else:
                success, result = commit_changes(self.repo, message=msg)
        except (ValueError, git.GitCommandError) as exc:
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
            if mode == "idea":
                changes = get_active_changelist(self.repo)
                message = self._commit_message() if changes.visible_paths else None
                selection = self._prepare_idea_selection()
            else:
                selection = get_publish_selection(self.repo, mode)
                message = self._commit_message() if selection.paths else None
            if selection is None:
                return
        except (ValueError, git.GitCommandError) as exc:
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
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - 540) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - 190) // 2)
        dialog.geometry(f"540x190+{x}+{y}")
        dialog.resizable(False, False)
        dialog.configure(background=palette(self.theme)["surface"])
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(dialog, text="Publishing branch", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=24, pady=(22, 8))
        stage_var = tk.StringVar(value="Starting…")
        ttk.Label(dialog, textvariable=stage_var).pack(anchor="w", padx=24, pady=(0, 12))
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=480)
        progress.pack(fill="x", padx=24)
        progress.start(12)
        ttk.Label(dialog, text="Network steps may take some time. Current step is shown above.",
                  style="Muted.TLabel").pack(anchor="w", padx=24, pady=14)
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
