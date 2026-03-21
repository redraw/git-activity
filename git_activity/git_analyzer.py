"""Git repository analyzer for extracting activity metrics."""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from collections import defaultdict

import git
from git import Repo, GitCommandError


class GitAnalyzer:
    """Analyzes git repository to extract file/folder activity metrics."""

    def __init__(self, repo_path: str):
        """Initialize analyzer with repository path.

        Args:
            repo_path: Path to git repository

        Raises:
            git.InvalidGitRepositoryError: If path is not a git repository
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo = Repo(repo_path)
        self._cache = {}
        self._file_commit_hashes = {}
        # author data structures
        self._file_author_commits: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
        self._author_stats: Dict[str, Dict] = defaultdict(lambda: {"commits": set(), "files": set(), "first_ts": None, "last_ts": None})
        self._commit_dates: Dict[str, int] = {}  # hash -> timestamp

    def get_file_activity(self, file_path: str) -> Tuple[Optional[datetime], int]:
        """Get activity metrics for a specific file.

        Args:
            file_path: Path to file relative to repository root

        Returns:
            Tuple of (last_commit_date, commit_count)
        """
        if file_path in self._cache:
            return self._cache[file_path]

        try:
            # Get commits that modified this file
            commits = list(self.repo.iter_commits(paths=file_path, max_count=1000))

            if not commits:
                self._cache[file_path] = (None, 0)
                return (None, 0)

            # Most recent commit is first
            last_date = datetime.fromtimestamp(commits[0].committed_date)
            count = len(commits)

            self._cache[file_path] = (last_date, count)
            return (last_date, count)

        except GitCommandError:
            self._cache[file_path] = (None, 0)
            return (None, 0)

    def get_directory_activity(self, dir_path: str) -> Tuple[Optional[datetime], int]:
        """Get aggregated activity metrics for a directory.

        Args:
            dir_path: Path to directory relative to repository root

        Returns:
            Tuple of (most_recent_commit_date, unique_commit_count)
        """
        if dir_path in self._cache:
            return self._cache[dir_path]

        try:
            # Get all commits that modified files in this directory
            commits = list(self.repo.iter_commits(paths=dir_path, max_count=1000))

            if not commits:
                self._cache[dir_path] = (None, 0)
                return (None, 0)

            # Most recent commit
            last_date = datetime.fromtimestamp(commits[0].committed_date)
            # Count unique commits by SHA
            count = len(set(commit.hexsha for commit in commits))

            self._cache[dir_path] = (last_date, count)
            return (last_date, count)

        except GitCommandError:
            self._cache[dir_path] = (None, 0)
            return (None, 0)

    def get_all_files_activity(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Tuple[Optional[datetime], int]]:
        """Get activity for all tracked files in repository using optimized batch processing.

        Args:
            progress_callback: Optional callback function(current, total) for progress updates

        Returns:
            Dictionary mapping file paths to (last_commit_date, commit_count)
        """
        activity = {}

        try:
            # Get all tracked files
            tracked_files = self.repo.git.ls_files().split('\n')
            tracked_files = [f for f in tracked_files if f]  # Filter empty strings
            total = len(tracked_files)

            # Use git log with name-only to get all file modifications in one go
            # Format: commit_hash|commit_timestamp|author_name
            log_output = self.repo.git.log(
                '--all',
                '--name-only',
                '--format=%H|%ct|%an',
                '--',
                *tracked_files
            )

            # Parse the log output
            file_commits = defaultdict(list)
            current_commit = None
            current_timestamp = None
            current_author = None

            for line in log_output.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Check if this is a commit line (contains |)
                if '|' in line:
                    parts = line.split('|', maxsplit=2)
                    if len(parts) == 3:
                        current_commit = parts[0]
                        current_timestamp = int(parts[1])
                        current_author = parts[2]
                        self._commit_dates[current_commit] = current_timestamp
                elif current_commit and line in tracked_files:
                    # This is a file that was modified in the current commit
                    file_commits[line].append((current_commit, current_timestamp))
                    # Track per-file author commits
                    self._file_author_commits[line][current_author].append(current_timestamp)
                    # Track global author stats
                    stats = self._author_stats[current_author]
                    stats["commits"].add(current_commit)
                    stats["files"].add(line)
                    if stats["last_ts"] is None or current_timestamp > stats["last_ts"]:
                        stats["last_ts"] = current_timestamp
                    if stats["first_ts"] is None or current_timestamp < stats["first_ts"]:
                        stats["first_ts"] = current_timestamp

            # Process each tracked file
            for idx, file_path in enumerate(tracked_files):
                if file_path in file_commits:
                    commits_data = file_commits[file_path]
                    # Most recent is first (git log is newest first)
                    last_date = datetime.fromtimestamp(commits_data[0][1])
                    count = len(commits_data)
                    activity[file_path] = (last_date, count)

                    # Store commit hashes for directory aggregation
                    self._file_commit_hashes[file_path] = [commit_hash for commit_hash, _ in commits_data]
                else:
                    activity[file_path] = (None, 0)
                    self._file_commit_hashes[file_path] = []

                if progress_callback:
                    progress_callback(idx + 1, total)

        except GitCommandError:
            pass

        return activity

    def get_file_author_stats(self, file_path: str) -> List[Dict]:
        """Get per-author stats for a single file or directory.

        Args:
            file_path: Path relative to repo root (file or directory prefix)

        Returns:
            List of dicts with author, commits, last_date, sorted by commits desc
        """
        # Aggregate over all files matching the prefix
        combined: Dict[str, Dict] = defaultdict(lambda: {"commits": 0, "last_ts": None})
        prefix = file_path.rstrip("/")

        for fpath, author_map in self._file_author_commits.items():
            if fpath == prefix or fpath.startswith(prefix + "/"):
                for author, timestamps in author_map.items():
                    combined[author]["commits"] += len(timestamps)
                    max_ts = max(timestamps)
                    if combined[author]["last_ts"] is None or max_ts > combined[author]["last_ts"]:
                        combined[author]["last_ts"] = max_ts

        result = []
        for author, data in combined.items():
            result.append({
                "author": author,
                "commits": data["commits"],
                "last_date": datetime.fromtimestamp(data["last_ts"]) if data["last_ts"] else None,
            })
        result.sort(key=lambda x: x["commits"], reverse=True)
        return result

    def get_global_author_stats(self) -> List[Dict]:
        """Get global author stats across the entire repository.

        Returns:
            List of dicts with author, total_commits, files_touched, first_date, last_date
        """
        result = []
        for author, data in self._author_stats.items():
            result.append({
                "author": author,
                "total_commits": len(data["commits"]),
                "files_touched": len(data["files"]),
                "first_date": datetime.fromtimestamp(data["first_ts"]) if data["first_ts"] else None,
                "last_date": datetime.fromtimestamp(data["last_ts"]) if data["last_ts"] else None,
            })
        result.sort(key=lambda x: x["total_commits"], reverse=True)
        return result

    def merge_authors(self, author_names: List[str], target_name: str) -> None:
        """Merge multiple authors into a single target author name.

        Args:
            author_names: All author names to merge (including target_name)
            target_name: The name to keep after merging
        """
        sources = [a for a in author_names if a != target_name]

        # Merge _author_stats
        if target_name not in self._author_stats:
            self._author_stats[target_name] = {"commits": set(), "files": set(), "first_ts": None, "last_ts": None}
        target_stats = self._author_stats[target_name]

        for src in sources:
            if src in self._author_stats:
                src_stats = self._author_stats[src]
                target_stats["commits"].update(src_stats["commits"])
                target_stats["files"].update(src_stats["files"])
                if src_stats["first_ts"] is not None:
                    if target_stats["first_ts"] is None or src_stats["first_ts"] < target_stats["first_ts"]:
                        target_stats["first_ts"] = src_stats["first_ts"]
                if src_stats["last_ts"] is not None:
                    if target_stats["last_ts"] is None or src_stats["last_ts"] > target_stats["last_ts"]:
                        target_stats["last_ts"] = src_stats["last_ts"]
                del self._author_stats[src]

        # Merge _file_author_commits
        for fpath, author_map in self._file_author_commits.items():
            for src in sources:
                if src in author_map:
                    author_map[target_name].extend(author_map.pop(src))

    def get_heatmap_data(self) -> Dict[str, int]:
        """Get commit counts per day for calendar heatmap.

        Returns:
            Dict mapping YYYY-MM-DD strings to commit count
        """
        day_counts: Dict[str, int] = defaultdict(int)
        for ts in self._commit_dates.values():
            day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            day_counts[day] += 1
        return dict(day_counts)

    def get_file_heatmap_data(self) -> List[Dict]:
        """Get per-file commit counts for file-grid heatmap.

        Returns:
            List of dicts with path, commit_count, last_date; sorted by commit_count desc
        """
        result = []
        for file_path, author_map in self._file_author_commits.items():
            total = sum(len(ts) for ts in author_map.values())
            all_ts = [ts for timestamps in author_map.values() for ts in timestamps]
            last_date = datetime.fromtimestamp(max(all_ts)) if all_ts else None
            result.append({"path": file_path, "commit_count": total, "last_date": last_date})
        result.sort(key=lambda x: x["commit_count"], reverse=True)
        return result

    def build_tree_with_activity(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict:
        """Build a tree structure with activity metrics.

        Args:
            progress_callback: Optional callback function(current, total) for progress updates

        Returns:
            Nested dictionary representing file tree with activity data
        """
        tree = {}
        activity = self.get_all_files_activity(progress_callback)

        for file_path, (last_date, count) in activity.items():
            parts = Path(file_path).parts
            current = tree

            # Build nested structure
            for i, part in enumerate(parts):
                if part not in current:
                    is_file = i == len(parts) - 1
                    current[part] = {
                        '_type': 'file' if is_file else 'dir',
                        '_path': str(Path(*parts[:i+1])),
                        '_last_commit': last_date if is_file else None,
                        '_commit_count': count if is_file else 0,
                        '_children': {} if not is_file else None
                    }

                if current[part]['_type'] == 'dir':
                    current = current[part]['_children']

        # Calculate directory metrics by aggregating children
        self._aggregate_dir_metrics(tree)

        return tree

    def _aggregate_dir_metrics(self, tree: Dict, current_path: str = "") -> Tuple[Optional[datetime], int]:
        """Recursively aggregate metrics for directories from children.

        Args:
            tree: Tree node dictionary
            current_path: Current directory path

        Returns:
            Tuple of (most_recent_date, unique_commit_count) for this node
        """
        if not tree:
            return (None, 0)

        most_recent = None
        unique_commits = set()

        for name, node in tree.items():
            if name.startswith('_'):
                continue

            if node['_type'] == 'dir':
                # Recursively process children first
                child_date, child_commits_set = self._aggregate_dir_metrics(node['_children'], node['_path'])

                node['_last_commit'] = child_date
                node['_commit_count'] = len(child_commits_set) if isinstance(child_commits_set, set) else child_commits_set

                # Add child commits to this directory's set
                if isinstance(child_commits_set, set):
                    unique_commits.update(child_commits_set)

                if child_date and (not most_recent or child_date > most_recent):
                    most_recent = child_date
            else:
                # File node - get its commit hashes
                file_path = node['_path']
                if file_path in self._file_commit_hashes:
                    file_hashes = self._file_commit_hashes[file_path]
                    unique_commits.update(file_hashes)

                if node['_last_commit'] and (not most_recent or node['_last_commit'] > most_recent):
                    most_recent = node['_last_commit']

        return (most_recent, unique_commits)
