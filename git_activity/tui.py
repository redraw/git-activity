"""TUI interface for git activity browser."""

from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Tree, Header, Footer, Static, DataTable, ProgressBar, Label
from textual.binding import Binding
from textual.reactive import reactive
from textual.worker import Worker, WorkerState
from rich.text import Text
from rich.style import Style

from git_activity.git_analyzer import GitAnalyzer


class ActivityTree(Tree):
    """Custom tree widget for displaying git activity."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "collapse_node", "Collapse", show=False),
        Binding("l", "expand_node", "Expand", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_root = False

    def action_collapse_node(self) -> None:
        """Collapse the currently selected node."""
        if self.cursor_node:
            self.cursor_node.collapse()

    def action_expand_node(self) -> None:
        """Expand the currently selected node."""
        if self.cursor_node:
            self.cursor_node.expand()


class ActivityTable(DataTable):
    """Custom data table with vim bindings."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]


class AuthorTable(DataTable):
    """Table for per-file/directory author stats."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("tab", "toggle_select", "Select", show=False),
        Binding("enter", "confirm_merge", "Merge", show=False),
        Binding("escape", "cancel_selection", "Cancel", show=False),
    ]

    def action_toggle_select(self) -> None:
        self.app._toggle_author_select(self.id)

    def action_confirm_merge(self) -> None:
        self.app._merge_selected_authors()

    def action_cancel_selection(self) -> None:
        self.app._cancel_author_selection()


class GlobalAuthorTable(DataTable):
    """Table for global repository author stats."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("tab", "toggle_select", "Select", show=False),
        Binding("enter", "confirm_merge", "Merge", show=False),
        Binding("escape", "cancel_selection", "Cancel", show=False),
    ]

    def action_toggle_select(self) -> None:
        self.app._toggle_author_select(self.id)

    def action_confirm_merge(self) -> None:
        self.app._merge_selected_authors()

    def action_cancel_selection(self) -> None:
        self.app._cancel_author_selection()


class HeatmapWidget(Static):
    """Heatmap view with calendar and file-grid sub-modes."""

    heatmap_mode = reactive("calendar")  # "calendar" or "files"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._calendar_data: dict = {}
        self._file_data: list = []
        self._max_commits = 1

    def set_data(self, calendar_data: dict, file_data: list) -> None:
        self._calendar_data = calendar_data
        self._file_data = file_data
        self._max_commits = max((v for v in calendar_data.values()), default=1)
        self._render_view()

    def toggle_mode(self) -> None:
        self.heatmap_mode = "files" if self.heatmap_mode == "calendar" else "calendar"
        self._render_view()

    def _render_view(self) -> None:
        if self.heatmap_mode == "calendar":
            self.update(self._render_calendar())
        else:
            self.update(self._render_file_grid())

    def _render_calendar(self) -> Text:
        from datetime import date, timedelta
        LEVELS = [" ", "░", "▒", "▓", "█"]
        COLORS = ["#333333", "#0e4429", "#006d32", "#26a641", "#39d353"]

        today = date.today()
        # Start from 52 weeks ago, on a Monday
        start = today - timedelta(weeks=52)
        start = start - timedelta(days=start.weekday())  # align to Monday

        # Build week columns
        weeks: list[list[tuple[date, int]]] = []
        current = start
        while current <= today:
            week = []
            for d in range(7):
                day = current + timedelta(days=d)
                count = self._calendar_data.get(day.strftime("%Y-%m-%d"), 0)
                week.append((day, count))
            weeks.append(week)
            current += timedelta(weeks=1)

        max_count = max((c for w in weeks for _, c in w), default=1)

        text = Text()
        # Month labels row
        text.append("     ")
        prev_month = None
        for week in weeks:
            month = week[0][0].strftime("%b")
            if month != prev_month:
                text.append(f"{month[:1]}", style="bold white")
                prev_month = month
            else:
                text.append(" ")
        text.append("\n")

        # Day rows (Mon=0 .. Sun=6)
        day_labels = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for d in range(7):
            text.append(f"{day_labels[d]} ", style="dim")
            for week in weeks:
                day_date, count = week[d]
                if day_date > today:
                    text.append(" ", style="dim")
                else:
                    level = 0 if count == 0 else max(1, int(count / max_count * 4) + 1)
                    level = min(level, 4)
                    text.append(LEVELS[level], style=f"{COLORS[level]}")
            text.append("\n")

        text.append("\n")
        text.append("  Less ", style="dim")
        for i, (lvl, col) in enumerate(zip(LEVELS, COLORS)):
            text.append(lvl, style=col)
        text.append("  More", style="dim")
        text.append(f"    (h to switch to file grid view)", style="dim")
        return text

    def _render_file_grid(self) -> Text:
        COLORS = ["#444444", "#0e4429", "#006d32", "#26a641", "#39d353"]
        max_count = max((f["commit_count"] for f in self._file_data), default=1)
        max_bar = 20

        text = Text()
        text.append("File Heatmap", style="bold white")
        text.append("    (h to switch to calendar view)\n\n", style="dim")

        for item in self._file_data[:200]:  # cap at 200 files
            count = item["commit_count"]
            path = item["path"]
            level = 0 if count == 0 else max(1, int(count / max_count * 4) + 1)
            level = min(level, 4)
            bar_width = max(1, int(count / max_count * max_bar))
            bar = "█" * bar_width
            empty = "░" * (max_bar - bar_width)

            text.append(f"{path:<50}", style=COLORS[level])
            text.append(f" {bar}", style=COLORS[level])
            text.append(empty, style="#333333")
            text.append(f" {count:>4}\n", style="dim")

        return text


class GitActivityApp(App):
    """A Textual app for browsing git repository activity."""

    CSS = """
    Screen {
        background: $surface;
    }

    #loading-container {
        align: center middle;
        height: 100%;
        width: 100%;
    }

    #loading-box {
        width: 60;
        height: auto;
        background: $panel;
        border: solid $primary;
        padding: 2;
    }

    #progress-label {
        text-align: center;
        margin-bottom: 1;
    }

    #stats {
        background: $panel;
        height: auto;
        padding: 1;
        margin-bottom: 1;
    }

    ActivityTree {
        border: solid $primary;
        height: 1fr;
    }

    DataTable {
        height: 1fr;
        border: solid $primary;
    }

    .recent {
        color: $success;
    }

    .moderate {
        color: $warning;
    }

    .old {
        color: $error;
    }

    .inactive {
        color: $text-muted;
    }

    #author-table {
        height: 1fr;
        border: solid $primary;
    }

    #global-author-table {
        height: 1fr;
        border: solid $primary;
    }

    #heatmap-view {
        height: 1fr;
        border: solid $primary;
        overflow-y: auto;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("v", "toggle_view", "Cycle View"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "author_view", "Authors"),
        Binding("1", "view_1", "Tree", show=False),
        Binding("2", "view_2", "Table", show=False),
        Binding("3", "view_3", "Authors", show=False),
        Binding("4", "view_4", "Global Authors", show=False),
        Binding("5", "view_5", "Heatmap", show=False),
        Binding("h", "toggle_heatmap_mode", "Heatmap Mode", show=False),
    ]

    view_mode = reactive("tree")  # "tree" | "table" | "authors" | "global_authors" | "heatmap"
    sort_mode = reactive("name")  # "name", "date", "commits", "files"

    def __init__(self, repo_path: str = "."):
        super().__init__()
        self.repo_path = Path(repo_path).resolve()
        self.analyzer = GitAnalyzer(str(self.repo_path))
        self.tree_data = None
        self.flat_data = []
        self.loading = True
        self.progress_current = 0
        self.progress_total = 0
        self._author_context_path = ""  # path shown in author view
        self._selected_authors: set = set()  # authors currently selected for merge

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Container(
            Container(
                Container(
                    Label("Loading repository data...", id="progress-label"),
                    ProgressBar(total=100, show_eta=False, id="progress-bar"),
                    id="loading-box"
                ),
                id="loading-container"
            ),
            Static(id="stats"),
            ActivityTree("Repository", id="file-tree"),
            ActivityTable(id="file-table"),
            AuthorTable(id="author-table"),
            GlobalAuthorTable(id="global-author-table"),
            HeatmapWidget(id="heatmap-view"),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the application on mount."""
        self.title = "Git Activity Browser"
        self.sub_title = f"Analyzing: {self.repo_path.name}"

        # Hide views initially
        self.query_one("#stats").display = False
        self.query_one("#file-tree").display = False
        self.query_one("#file-table").display = False
        self.query_one("#author-table").display = False
        self.query_one("#global-author-table").display = False
        self.query_one("#heatmap-view").display = False

        # Start loading data in background
        self.load_data()

    def load_data(self) -> None:
        """Load git data with progress tracking."""
        self.run_worker(self._load_data_worker, exclusive=True, thread=True)

    def _load_data_worker(self) -> None:
        """Worker function to load data in background."""
        def progress_callback(current: int, total: int):
            self.progress_current = current
            self.progress_total = total
            self.call_from_thread(self._update_progress)

        # Build tree data with progress
        self.tree_data = self.analyzer.build_tree_with_activity(progress_callback)

        # Signal completion
        self.call_from_thread(self._on_data_loaded)

    def _update_progress(self) -> None:
        """Update progress bar from main thread."""
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        label = self.query_one("#progress-label", Label)

        if self.progress_total > 0:
            progress_bar.update(total=self.progress_total, progress=self.progress_current)
            label.update(f"Analyzing files... {self.progress_current}/{self.progress_total}")

    def _on_data_loaded(self) -> None:
        """Called when data loading is complete."""
        self.loading = False

        # Hide loading UI
        self.query_one("#loading-container").display = False

        # Show main UI
        self.query_one("#stats").display = True
        self.query_one("#file-tree").display = True

        # Initialize views
        self._populate_tree()
        self._populate_table()
        self._populate_global_author_table()
        self._populate_heatmap()

        # Show tree by default
        self._update_view()

    def _populate_tree(self) -> None:
        """Populate the tree view with git activity data."""
        tree = self.query_one("#file-tree", ActivityTree)
        tree.clear()

        root = tree.root
        root.expand()

        # Calculate max commits for histogram scaling
        self.max_commits = self._find_max_commits(self.tree_data)

        self._add_tree_nodes(root, self.tree_data)

    def _find_max_commits(self, data: Dict) -> int:
        """Find the maximum commit count in the tree for scaling histogram.

        Args:
            data: Tree data dictionary

        Returns:
            Maximum commit count
        """
        max_count = 0
        for name, node in data.items():
            if name.startswith('_'):
                continue

            count = node.get('_commit_count', 0)
            if count > max_count:
                max_count = count

            if node['_type'] == 'dir' and '_children' in node:
                child_max = self._find_max_commits(node['_children'])
                if child_max > max_count:
                    max_count = child_max

        return max_count

    def _add_tree_nodes(self, parent_node, data: Dict, path: str = "") -> None:
        """Recursively add nodes to tree.

        Args:
            parent_node: Parent tree node
            data: Dictionary of file/directory data
            path: Current path for tracking
        """
        # Sort items: directories first, then by name
        items = []
        for name, node in data.items():
            if name.startswith('_'):
                continue
            items.append((name, node))

        items.sort(key=lambda x: (x[1]['_type'] == 'file', x[0].lower()))

        for name, node in items:
            node_type = node['_type']
            last_commit = node.get('_last_commit')
            commit_count = node.get('_commit_count', 0)

            # Format label with activity info
            label = self._format_node_label(name, node_type, last_commit, commit_count)

            child = parent_node.add(label, data=node, allow_expand=node_type == 'dir')

            # Recursively add children for directories
            if node_type == 'dir' and '_children' in node:
                self._add_tree_nodes(child, node['_children'], node['_path'])

    def _format_node_label(
        self,
        name: str,
        node_type: str,
        last_commit: Optional[datetime],
        commit_count: int
    ) -> Text:
        """Format a tree node label with color coding.

        Args:
            name: File or directory name
            node_type: 'file' or 'dir'
            last_commit: Last commit datetime
            commit_count: Number of commits

        Returns:
            Formatted Rich Text object
        """
        # Icon based on type
        icon = "📁" if node_type == "dir" else "📄"

        # Format date
        if last_commit:
            date_str = last_commit.strftime("%Y-%m-%d")
            days_ago = (datetime.now() - last_commit).days

            # Color code based on recency
            if days_ago < 7:
                style = "recent"
            elif days_ago < 30:
                style = "moderate"
            elif days_ago < 90:
                style = "old"
            else:
                style = "inactive"
        else:
            date_str = "N/A"
            style = "inactive"
            days_ago = float('inf')

        # Build label
        text = Text()
        # Add spaces for files to align with folders (which have expand arrow + space)
        if node_type == "file":
            text.append("  ")
        text.append(f"{icon} ", style="bold")
        text.append(f"{name:<40}", style="bold" if node_type == "dir" else "")
        text.append(f" │ ", style="dim")
        text.append(f"{date_str:>10}", style=style)
        text.append(f" │ ", style="dim")
        text.append(f"{commit_count:>4} commits", style=style)
        text.append(" ", style="dim")

        # Add histogram bar
        histogram = self._create_histogram(commit_count)
        text.append(histogram)

        return text

    def _create_histogram(self, commit_count: int) -> Text:
        """Create a histogram bar for commit count.

        Args:
            commit_count: Number of commits

        Returns:
            Text object with histogram bar
        """
        max_bar_width = 15

        if not hasattr(self, 'max_commits') or self.max_commits == 0:
            bar_width = 0
        else:
            # Scale to max_bar_width
            bar_width = int((commit_count / self.max_commits) * max_bar_width)

        # Use block characters for the bar
        bar = "█" * bar_width
        empty = "░" * (max_bar_width - bar_width)

        histogram = Text()
        histogram.append(bar, style="green")
        histogram.append(empty, style="dim")

        return histogram

    def _populate_table(self) -> None:
        """Populate the table view with git activity data."""
        table = self.query_one("#file-table", ActivityTable)
        table.clear(columns=True)

        # Add columns (removed Name column, only showing Path)
        table.add_column("Path", key="path", width=60)
        table.add_column("Type", key="type", width=8)
        table.add_column("Last Updated", key="date", width=12)
        table.add_column("Commits", key="commits", width=10)

        # Flatten tree data
        self.flat_data = []
        self._flatten_tree(self.tree_data, self.flat_data)

        # Sort data
        self._sort_flat_data()

        # Add rows
        for item in self.flat_data:
            node_type = "Dir" if item['type'] == 'dir' else "File"
            last_commit = item['last_commit']
            commit_count = item['commit_count']
            path = item['path']

            date_str = last_commit.strftime("%Y-%m-%d") if last_commit else "N/A"

            # Color code
            style_name = self._get_style_for_date(last_commit)

            table.add_row(
                Text(path, style=style_name),
                Text(node_type, style="dim"),
                Text(date_str, style=style_name),
                Text(str(commit_count), style=style_name),
            )

    def _flatten_tree(self, data: Dict, result: list, parent_path: str = "") -> None:
        """Flatten tree structure into a list.

        Args:
            data: Dictionary of file/directory data
            result: List to append flattened items
            parent_path: Parent directory path
        """
        for name, node in data.items():
            if name.startswith('_'):
                continue

            path = node['_path']
            result.append({
                'name': name,
                'type': node['_type'],
                'last_commit': node.get('_last_commit'),
                'commit_count': node.get('_commit_count', 0),
                'path': path,
            })

            if node['_type'] == 'dir' and '_children' in node:
                self._flatten_tree(node['_children'], result, path)

    def _sort_flat_data(self) -> None:
        """Sort flat data based on current sort mode."""
        if self.sort_mode == "name":
            self.flat_data.sort(key=lambda x: (x['type'] == 'file', x['name'].lower()))
        elif self.sort_mode == "date":
            self.flat_data.sort(
                key=lambda x: (x['last_commit'] is None, x['last_commit']),
                reverse=True
            )
        elif self.sort_mode == "commits":
            self.flat_data.sort(key=lambda x: x['commit_count'], reverse=True)

    def _get_style_for_date(self, last_commit: Optional[datetime]) -> str:
        """Get color style based on date recency.

        Args:
            last_commit: Last commit datetime

        Returns:
            Style name string
        """
        if not last_commit:
            return "inactive"

        days_ago = (datetime.now() - last_commit).days

        if days_ago < 7:
            return "recent"
        elif days_ago < 30:
            return "moderate"
        elif days_ago < 90:
            return "old"
        else:
            return "inactive"

    def _populate_author_table(self, path: str) -> None:
        """Populate per-file/directory author table."""
        table = self.query_one("#author-table", AuthorTable)
        prev_cursor = table.cursor_row
        table.clear(columns=True)
        table.add_column("Author", key="author", width=32)
        table.add_column("Commits", key="commits", width=10)
        table.add_column("%", key="pct", width=6)
        table.add_column("Last Commit", key="last", width=12)

        data = self.analyzer.get_file_author_stats(path) if path else self.analyzer.get_global_author_stats()
        if not data:
            return

        # Normalize to common keys
        if path:
            rows = data
            total = sum(r["commits"] for r in rows)
        else:
            rows = [{"author": r["author"], "commits": r["total_commits"], "last_date": r["last_date"]} for r in data]
            total = sum(r["total_commits"] for r in data)

        # Sort
        if self.sort_mode == "name":
            rows.sort(key=lambda x: x["author"].lower())
        else:
            rows.sort(key=lambda x: x["commits"], reverse=True)

        for row in rows:
            author = row["author"]
            selected = author in self._selected_authors
            pct = f"{row['commits'] / total * 100:.0f}%" if total > 0 else "0%"
            last_date = row.get("last_date")
            date_str = last_date.strftime("%Y-%m-%d") if last_date else "N/A"
            style = "bold white on #2a2a5a" if selected else self._get_style_for_date(last_date)
            marker = "✓ " if selected else "  "
            table.add_row(
                Text(marker + author, style=style),
                Text(str(row["commits"]), style=style),
                Text(pct, style="dim" if not selected else style),
                Text(date_str, style=style),
            )

        # Restore cursor position
        if prev_cursor > 0 and prev_cursor < table.row_count:
            table.move_cursor(row=prev_cursor)

    def _populate_global_author_table(self) -> None:
        """Populate global author stats table."""
        table = self.query_one("#global-author-table", GlobalAuthorTable)
        prev_cursor = table.cursor_row
        table.clear(columns=True)
        table.add_column("Author", key="author", width=32)
        table.add_column("Commits", key="commits", width=10)
        table.add_column("Files", key="files", width=8)
        table.add_column("First Commit", key="first", width=12)
        table.add_column("Last Commit", key="last", width=12)

        data = self.analyzer.get_global_author_stats()

        if self.sort_mode == "name":
            data.sort(key=lambda x: x["author"].lower())
        elif self.sort_mode == "files":
            data.sort(key=lambda x: x["files_touched"], reverse=True)
        elif self.sort_mode == "date":
            data.sort(key=lambda x: (x["last_date"] is None, x["last_date"]), reverse=True)
        else:  # commits
            data.sort(key=lambda x: x["total_commits"], reverse=True)

        for row in data:
            author = row["author"]
            selected = author in self._selected_authors
            style = "bold white on #2a2a5a" if selected else self._get_style_for_date(row["last_date"])
            marker = "✓ " if selected else "  "
            first_str = row["first_date"].strftime("%Y-%m-%d") if row["first_date"] else "N/A"
            last_str = row["last_date"].strftime("%Y-%m-%d") if row["last_date"] else "N/A"
            table.add_row(
                Text(marker + author, style=style),
                Text(str(row["total_commits"]), style=style),
                Text(str(row["files_touched"]), style="dim" if not selected else style),
                Text(first_str, style="dim" if not selected else style),
                Text(last_str, style=style),
            )

        # Restore cursor position
        if prev_cursor > 0 and prev_cursor < table.row_count:
            table.move_cursor(row=prev_cursor)

    def _populate_heatmap(self) -> None:
        """Populate heatmap widget with data."""
        heatmap = self.query_one("#heatmap-view", HeatmapWidget)
        calendar_data = self.analyzer.get_heatmap_data()
        file_data = self.analyzer.get_file_heatmap_data()
        heatmap.set_data(calendar_data, file_data)

    def _update_view(self) -> None:
        """Update visibility based on current view mode."""
        widgets = {
            "tree": self.query_one("#file-tree"),
            "table": self.query_one("#file-table"),
            "authors": self.query_one("#author-table"),
            "global_authors": self.query_one("#global-author-table"),
            "heatmap": self.query_one("#heatmap-view"),
        }
        for mode, widget in widgets.items():
            widget.display = (mode == self.view_mode)

        widgets[self.view_mode].focus()
        self._update_stats()

    def _update_stats(self) -> None:
        """Update statistics display."""
        stats = self.query_one("#stats", Static)

        total_items = len(self.flat_data)
        files = sum(1 for item in self.flat_data if item['type'] == 'file')
        dirs = total_items - files

        view_names = {
            "tree": "Tree [1]",
            "table": "Table [2]",
            "authors": f"Authors: {self._author_context_path or 'repo'} [3]",
            "global_authors": "Global Authors [4]",
            "heatmap": "Heatmap [5]",
        }
        view_name = view_names.get(self.view_mode, self.view_mode)
        sort_name = self.sort_mode.title()

        base = f"View: {view_name} | Sort: {sort_name} | Files: {files} | Dirs: {dirs} | [v] cycle"
        if self._selected_authors and self.view_mode in ("authors", "global_authors"):
            n = len(self._selected_authors)
            base += f" | [Tab] select  Selected: {n} — [Enter] merge, [Esc] cancel"
        elif self.view_mode in ("authors", "global_authors"):
            base += " | [Tab] select authors to merge"
        stats.update(base)

    def _get_author_at_cursor(self, table_id: str) -> Optional[str]:
        """Get the author name at the current cursor row of a table."""
        try:
            from textual.coordinate import Coordinate
            table = self.query_one(f"#{table_id}")
            cell = table.get_cell_at(Coordinate(table.cursor_row, 0))
            # Strip ✓ marker and leading spaces
            name = str(cell).lstrip("✓ ").strip()
            return name if name else None
        except Exception:
            return None

    def _toggle_author_select(self, table_id: Optional[str] = None) -> None:
        """Toggle the author at the current cursor in/out of the selection set."""
        tid = table_id or ("author-table" if self.view_mode == "authors" else "global-author-table")
        author = self._get_author_at_cursor(tid)
        if not author:
            return
        if author in self._selected_authors:
            self._selected_authors.discard(author)
        else:
            self._selected_authors.add(author)
        # Re-populate to reflect selection change, cursor is preserved inside populate
        if self.view_mode == "authors":
            self._populate_author_table(self._author_context_path)
        else:
            self._populate_global_author_table()
        # Move cursor down after toggling
        try:
            table = self.query_one(f"#{tid}")
            if table.cursor_row < table.row_count - 1:
                table.move_cursor(row=table.cursor_row + 1)
        except Exception:
            pass
        self._update_stats()

    def _merge_selected_authors(self) -> None:
        """Merge all selected authors into the one with the most commits."""
        if len(self._selected_authors) < 2:
            return
        # Pick target: author with most total commits among selected
        global_stats = {r["author"]: r["total_commits"] for r in self.analyzer.get_global_author_stats()}
        target = max(self._selected_authors, key=lambda a: global_stats.get(a, 0))
        self.analyzer.merge_authors(list(self._selected_authors), target)
        self._selected_authors.clear()
        # Refresh both author views
        self._populate_author_table(self._author_context_path)
        self._populate_global_author_table()
        self._update_stats()

    def _cancel_author_selection(self) -> None:
        """Clear the current author selection."""
        self._selected_authors.clear()
        if self.view_mode == "authors":
            self._populate_author_table(self._author_context_path)
        else:
            self._populate_global_author_table()
        self._update_stats()

    def action_toggle_view(self) -> None:
        """Cycle through all view modes."""
        modes = ["tree", "table", "authors", "global_authors", "heatmap"]
        current_idx = modes.index(self.view_mode) if self.view_mode in modes else 0
        self.view_mode = modes[(current_idx + 1) % len(modes)]
        self._update_view()

    def action_view_1(self) -> None:
        self.view_mode = "tree"
        self._update_view()

    def action_view_2(self) -> None:
        self.view_mode = "table"
        self._update_view()

    def action_view_3(self) -> None:
        self._author_context_path = ""
        self._populate_author_table("")
        self.view_mode = "authors"
        self._update_view()

    def action_view_4(self) -> None:
        self.view_mode = "global_authors"
        self._update_view()

    def action_view_5(self) -> None:
        self.view_mode = "heatmap"
        self._update_view()

    def action_author_view(self) -> None:
        """Switch to author view for the currently selected file/directory."""
        if self.loading:
            return
        path = ""
        if self.view_mode == "tree":
            tree = self.query_one("#file-tree", ActivityTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.get("_path", "")
        elif self.view_mode == "table":
            table = self.query_one("#file-table", ActivityTable)
            row = table.cursor_row
            if 0 <= row < len(self.flat_data):
                path = self.flat_data[row]["path"]
        self._author_context_path = path
        self._populate_author_table(path)
        self.view_mode = "authors"
        self._update_view()

    def action_toggle_heatmap_mode(self) -> None:
        """Toggle heatmap sub-mode (only active when in heatmap view)."""
        if self.view_mode == "heatmap":
            self.query_one("#heatmap-view", HeatmapWidget).toggle_mode()

    def action_cycle_sort(self) -> None:
        """Cycle through sort modes (context-sensitive)."""
        sort_options = {
            "tree": ["name", "date", "commits"],
            "table": ["name", "date", "commits"],
            "authors": ["commits", "name"],
            "global_authors": ["commits", "name", "files", "date"],
            "heatmap": ["commits", "name", "date"],
        }
        modes = sort_options.get(self.view_mode, ["name", "date", "commits"])
        current = self.sort_mode if self.sort_mode in modes else modes[0]
        self.sort_mode = modes[(modes.index(current) + 1) % len(modes)]

        if self.view_mode in ("tree", "table"):
            self._populate_table()
        elif self.view_mode == "authors":
            self._populate_author_table(self._author_context_path)
        elif self.view_mode == "global_authors":
            self._populate_global_author_table()
        self._update_stats()

    def action_refresh(self) -> None:
        """Refresh the data from git repository."""
        if self.loading:
            return

        # Show loading UI
        self.loading = True
        self.query_one("#loading-container").display = True
        self.query_one("#stats").display = False
        self.query_one("#file-tree").display = False
        self.query_one("#file-table").display = False
        self.query_one("#author-table").display = False
        self.query_one("#global-author-table").display = False
        self.query_one("#heatmap-view").display = False

        # Clear selection state
        self._selected_authors.clear()

        # Reset author data structures
        from collections import defaultdict
        self.analyzer._file_author_commits = defaultdict(lambda: defaultdict(list))
        self.analyzer._author_stats = defaultdict(lambda: {"commits": set(), "files": set(), "first_ts": None, "last_ts": None})
        self.analyzer._commit_dates = {}

        # Clear cache and reload
        self.analyzer._cache.clear()
        self.load_data()


def run_tui(repo_path: str = ".") -> None:
    """Run the TUI application.

    Args:
        repo_path: Path to git repository (default: current directory)
    """
    app = GitActivityApp(repo_path)
    app.run()
