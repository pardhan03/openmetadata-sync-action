"""
file_detector.py — Detects which schema-related files changed in a PR or push.
Enhanced with detailed logging for debugging & demo visibility.
"""

import os
import subprocess
from rich.console import Console

console = Console()

SUPPORTED_EXTENSIONS = {".yml", ".yaml", ".sql", ".json"}
IGNORE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "package.json", "package-lock.json", "tsconfig.json"
}


def detect_changed_files(schema_path: str, workspace: str) -> list[str]:
    console.rule("[bold blue]📂 FILE DETECTION STARTED")

    console.print(f"📁 Workspace: {workspace}")
    console.print(f"📁 Schema Path: {schema_path}")

    changed = _get_git_diff_files(workspace)

    if not changed:
        console.print("⚠️ No git diff found → scanning all schema files", style="yellow")
        changed = _scan_directory(schema_path, workspace)
        console.print(f"📦 Found {len(changed)} files via fallback scan")

    filtered = _filter_files(changed, schema_path)

    console.print(f" Final filtered files: {len(filtered)}", style="green")
    for f in filtered:
        console.print(f"   → {f}")

    console.rule("[bold green]📂 FILE DETECTION COMPLETED")
    return filtered


def _get_git_diff_files(workspace: str) -> list[str]:
    try:
        os.chdir(workspace)

        base_ref = os.environ.get("GITHUB_BASE_REF", "")
        head_ref = os.environ.get("GITHUB_HEAD_REF", "")

        console.print("\n🔍 [bold]Git Diff Detection[/bold]")
        console.print(f"   Base ref: {base_ref or 'N/A'}")
        console.print(f"   Head ref: {head_ref or 'N/A'}")

        # Strategy 1: PR diff (BEST CASE)
        if base_ref:
            console.print("➡️ Strategy 1: PR diff using base_ref", style="cyan")

            subprocess.run(["git", "fetch", "origin", base_ref], capture_output=True, check=False)

            result = subprocess.run(
                ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
                capture_output=True, text=True, check=False
            )

            if result.stdout.strip():
                files = _parse_git_output(result.stdout)
                console.print(f" Found {len(files)} file(s) via PR diff", style="green")
                return files
            else:
                console.print(" No files found in PR diff", style="red")

        # Strategy 2: Merge-base diff
        console.print(" Strategy 2: Merge-base diff", style="cyan")

        subprocess.run(["git", "fetch", "origin"], capture_output=True, check=False)

        for base in ["origin/main", "origin/master"]:
            result = subprocess.run(
                ["git", "merge-base", "HEAD", base],
                capture_output=True, text=True, check=False
            )

            if result.stdout.strip():
                merge_base = result.stdout.strip()
                console.print(f"   Using base: {base}")

                result2 = subprocess.run(
                    ["git", "diff", "--name-only", merge_base, "HEAD"],
                    capture_output=True, text=True, check=False
                )

                if result2.stdout.strip():
                    files = _parse_git_output(result2.stdout)
                    console.print(f" Found {len(files)} file(s) via merge-base", style="green")
                    return files

        # Strategy 3: Last commit diff
        console.print("➡️ Strategy 3: HEAD~1 diff", style="cyan")

        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, check=False
        )

        if result.stdout.strip():
            files = _parse_git_output(result.stdout)
            console.print(f"Found {len(files)} file(s) via last commit", style="green")
            return files

        console.print(" No files detected via any git strategy", style="red")

    except Exception as e:
        console.print(f"Git diff error: {e}", style="bold red")

    return []


def _scan_directory(schema_path: str, workspace: str) -> list[str]:
    console.print("\n📦 [bold]Fallback Directory Scan[/bold]")

    results = []
    full_path = os.path.join(workspace, schema_path)

    console.print(f"Scanning path: {full_path}")

    for root, dirs, files in os.walk(full_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_PATTERNS]

        for file in files:
            _, ext = os.path.splitext(file)

            if ext in SUPPORTED_EXTENSIONS:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, workspace)
                results.append(rel_path)
                console.print(f"   + Found: {rel_path}")

    return results


def _filter_files(files: list[str], schema_path: str) -> list[str]:
    console.print("\n🧹 [bold]Filtering Files[/bold]")

    filtered = []

    for filepath in files:
        if schema_path != "." and not filepath.startswith(schema_path):
            console.print(f"   Skipped (not in schema path): {filepath}")
            continue

        _, ext = os.path.splitext(filepath)
        if ext not in SUPPORTED_EXTENSIONS:
            console.print(f"   Skipped (unsupported type): {filepath}")
            continue

        parts = filepath.replace("\\", "/").split("/")
        if any(part in IGNORE_PATTERNS for part in parts):
            console.print(f"   Skipped (ignored path): {filepath}")
            continue

        console.print(f"   Accepted: {filepath}")
        filtered.append(filepath)

    return filtered


def _parse_git_output(output: str) -> list[str]:
    files = [f.strip() for f in output.strip().split("\n") if f.strip()]
    for f in files:
        console.print(f"   → Changed: {f}")
    return files