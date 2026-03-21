#!/usr/bin/env python3
"""Main entry point for git-activity CLI."""

import sys
import argparse
import tempfile
import shutil
from pathlib import Path

from git import InvalidGitRepositoryError, GitCommandError

from git_activity.tui import run_tui


def is_git_url(path: str) -> bool:
    """Check if the path is a git URL."""
    url_schemes = ['http://', 'https://', 'git://', 'ssh://', 'git@']
    return any(path.startswith(scheme) for scheme in url_schemes)


def main():
    """Main entry point for the git-activity command."""
    parser = argparse.ArgumentParser(
        prog="git-activity",
        description="Interactive TUI for browsing git repository activity",
        epilog="Navigate with arrow keys or hjkl, toggle views with 'v', sort with 's', quit with 'q'"
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to git repository or remote URL (default: current directory)"
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version="git-activity 0.1.0"
    )

    args = parser.parse_args()

    temp_dir = None

    try:
        from git import Repo

        # Check if it's a remote URL
        if is_git_url(args.path):
            print(f"Cloning repository from {args.path}...", file=sys.stderr)
            temp_dir = tempfile.mkdtemp(prefix="git-activity-")

            try:
                Repo.clone_from(args.path, temp_dir)
                repo_path = Path(temp_dir)
                print(f"Repository cloned to temporary location", file=sys.stderr)
            except GitCommandError as e:
                print(f"Error cloning repository: {e}", file=sys.stderr)
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                sys.exit(1)
        else:
            # Local path
            repo_path = Path(args.path).resolve()

            if not repo_path.exists():
                print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
                sys.exit(1)

            if not repo_path.is_dir():
                print(f"Error: Path is not a directory: {repo_path}", file=sys.stderr)
                sys.exit(1)

        # Check if it's a git repository
        try:
            repo = Repo(repo_path)

            # Verify it's not a bare repository
            if repo.bare:
                print(f"Error: Cannot analyze bare repository: {repo_path}", file=sys.stderr)
                sys.exit(1)

        except InvalidGitRepositoryError:
            print(f"Error: Not a git repository: {repo_path}", file=sys.stderr)
            print("Initialize a git repository first with: git init", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error accessing repository: {e}", file=sys.stderr)
            sys.exit(1)

        # Run the TUI
        try:
            run_tui(str(repo_path))
        except KeyboardInterrupt:
            print("\nInterrupted by user", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            print(f"Error running TUI: {e}", file=sys.stderr)
            sys.exit(1)

    finally:
        # Clean up temporary directory if created
        if temp_dir and Path(temp_dir).exists():
            print(f"Cleaning up temporary files...", file=sys.stderr)
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
