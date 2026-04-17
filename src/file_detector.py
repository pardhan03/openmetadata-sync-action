"""
file_detector.py — Detects which schema-related files changed in a PR or push.

In a GitHub Actions environment, we use git to find files that changed
compared to the base branch. Supports filtering by schema_path.
"""

import os
import subprocess
from rich.console import Console

console = Console()

# File extensions we care about
SUPPORTED_EXTENSIONS = {".yml", ".yaml", ".sql", ".json"}

# Directories/filenames to always ignore
IGNORE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "package.json", "package-lock.json", "tsconfig.json"
}


def detect_changed_files(schema_path: str, workspace: str) -> list[str]:
    """
    Detect files that changed in this PR/push and match our supported types.

    Strategy:
      1. Try git diff to get changed files (works in GitHub Actions)
      2. Fall back to scanning the schema_path directory (useful for local testing)

    Returns a list of relative file paths.
    """
    changed = _get_git_diff_files(workspace)

    if changed:
        console.print(f"  [dim]Git detected {len(changed)} total changed file(s)[/dim]")
    else:
        # Fallback: scan schema_path for all supported files
        console.print("  [dim]No git diff available. Scanning schema_path for all files...[/dim]")
        changed = _scan_directory(schema_path, workspace)

    # Filter to only supported schema files within schema_path
    filtered = _filter_files(changed, schema_path)
    return filtered


def _get_git_diff_files(workspace: str) -> list[str]:
    """
    Use git to find files changed vs the base branch (origin/main or origin/master).
    This is the standard way to detect changes inside GitHub Actions.
    """
    try:
        os.chdir(workspace)

        # Try fetching origin to get base branch info
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, check=False
        )

        # Try common base branch names
        for base_branch in ["origin/main", "origin/master"]:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_branch, "HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                return files

        # If no base branch found, get files changed in the last commit
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    except Exception as e:
        console.print(f"  [dim]Git diff error (non-fatal): {e}[/dim]")

    return []


def _scan_directory(schema_path: str, workspace: str) -> list[str]:
    """
    Recursively scan a directory for all supported schema files.
    Used as a fallback when git diff isn't available.
    """
    results = []
    full_path = os.path.join(workspace, schema_path)

    for root, dirs, files in os.walk(full_path):
        # Skip ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_PATTERNS]

        for file in files:
            _, ext = os.path.splitext(file)
            if ext in SUPPORTED_EXTENSIONS:
                abs_path = os.path.join(root, file)
                # Store as relative path from workspace
                rel_path = os.path.relpath(abs_path, workspace)
                results.append(rel_path)

    return results


def _filter_files(files: list[str], schema_path: str) -> list[str]:
    """
    Filter a list of file paths to only include:
    - Files within schema_path
    - Files with supported extensions
    - Files not matching ignore patterns
    """
    filtered = []

    for filepath in files:
        # Must be under schema_path
        if schema_path != "." and not filepath.startswith(schema_path):
            continue

        # Must have a supported extension
        _, ext = os.path.splitext(filepath)
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        # Must not match any ignore patterns
        parts = filepath.replace("\\", "/").split("/")
        if any(part in IGNORE_PATTERNS for part in parts):
            continue

        filtered.append(filepath)

    return filtered
