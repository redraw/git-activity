# Git Activity Browser

A Terminal User Interface (TUI) file browser that displays git activity metrics for files and directories. Quickly identify hot spots, stale code, and recent changes in your repository.

## Features

### Two View Modes
- **Tree View** - Hierarchical file browser with expandable directories
- **Table View** - Flat sortable list of all files and directories

### Activity Metrics
- **Last Updated** - Date of most recent commit affecting each file/folder
- **Commit Count** - Total number of commits for each file/folder
- **Color Coding** - Visual indicators for activity recency
  - 🟢 Green: Updated in last 7 days
  - 🟡 Yellow: Updated in last 30 days
  - 🟠 Orange: Updated in last 90 days
  - ⚪ Gray: Older than 90 days

### Interactive Features
- Real-time git analysis
- Multiple sort modes (name, date, commits)
- Keyboard-driven navigation
- Aggregated directory statistics

## Installation

### Using uv (recommended)
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### Using pip
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

## Quick Start

Run in current directory:
```bash
git-activity
```

Run in specific repository:
```bash
git-activity /path/to/repo
```

Try the demo with sample data:
```bash
./test_demo.sh
```

## Keyboard Controls

| Key | Action |
|-----|--------|
| `↑/↓` or `j/k` | Navigate up/down |
| `←/→` or `h/l` | Collapse/expand directories |
| `Enter` | Toggle directory expansion |
| `v` | Toggle tree/table view |
| `s` | Cycle sort mode |
| `r` | Refresh from git |
| `q` | Quit |

## Use Cases

- **Code Review** - Find recently modified code
- **Onboarding** - Identify active areas of the codebase
- **Refactoring** - Locate stale code needing attention
- **Hot Spots** - Discover frequently changed files
- **Maintenance** - Track file update patterns

## Requirements

- Python 3.8+
- Git repository with commits
- Terminal with ANSI color support

## Documentation

See [USAGE.md](USAGE.md) for detailed usage guide and tips.

## Technology

Built with:
- [Textual](https://textual.textualize.io/) - Modern TUI framework
- [GitPython](https://gitpython.readthedocs.io/) - Git integration
- [Rich](https://rich.readthedocs.io/) - Terminal formatting

## License

MIT
