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
        console.print(f"[green]Git detected {len(changed)} changed file(s)[/green]")
    else:
        console.print("[yellow]No git diff → scanning all schema files[/yellow]")
        changed = _scan_directory(schema_path, workspace)

        if changed:
            console.print(f"[green]Found {len(changed)} files via fallback[/green]")
        else:
            console.print("[red]No schema files found even in fallback[/red]")

    # Filter to only supported schema files within schema_path
    filtered = _filter_files(changed, schema_path)
    return filtered


def _get_git_diff_files(workspace: str) -> list[str]:
    """
    Detect changed files using PR base and HEAD.
    Works reliably in GitHub Actions PR context.
    """
    try:
        os.chdir(workspace)

        base_ref = os.getenv("GITHUB_BASE_REF")
        head_ref = os.getenv("GITHUB_HEAD_REF")

        console.print(f"[dim]Base ref: {base_ref} | Head ref: {head_ref}[/dim]")

        if not base_ref:
            console.print("[dim]No GITHUB_BASE_REF found → fallback[/dim]")
            return []

        # Fetch base branch explicitly
        subprocess.run(
            ["git", "fetch", "origin", base_ref],
            capture_output=True,
            check=False
        )

        # Proper PR diff
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]

            if files:
                console.print(f"[green]Detected changed files:[/green] {files}")
                return files
            else:
                console.print("[yellow]Git diff returned no changed files[/yellow]")

        console.print("[dim]No files detected via PR diff[/dim]")

    except Exception as e:
        console.print(f"[red]Git diff error:[/red] {e}")

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
        normalized_path = schema_path.strip("./")

        if schema_path != "." and not filepath.startswith(normalized_path):
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
