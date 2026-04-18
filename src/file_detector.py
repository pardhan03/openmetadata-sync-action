"""
file_detector.py — Detects which schema-related files changed in a PR or push.
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
    """
    Detect changed schema files in this PR.
    Falls back to scanning the directory if git diff fails.
    """
    # Normalize schema_path: strip leading ./ so "models/orders.yml".startswith("models") works
    normalized_path = schema_path.lstrip("./") if schema_path not in (".", "./") else ""

    changed = _get_git_diff_files(workspace)

    if not changed:
        console.print("  No git diff → scanning all schema files")
        changed = _scan_directory(normalized_path, workspace)
        console.print(f"  Found {len(changed)} files via fallback")

    filtered = _filter_files(changed, normalized_path)
    return filtered


def _get_git_diff_files(workspace: str) -> list[str]:
    """
    Detect files changed in this PR using multiple git strategies.
    """
    try:
        os.chdir(workspace)

        base_ref = os.environ.get("GITHUB_BASE_REF", "")
        head_ref = os.environ.get("GITHUB_HEAD_REF", "")
        console.print(f"  Base ref: {base_ref} | Head ref: {head_ref}")

        # Fetch all remote refs first so git diff has full history
        subprocess.run(["git", "fetch", "--all", "--depth=50"],
                       capture_output=True, check=False)

        # ── Strategy 1: fetch head branch explicitly then diff ────────────────
        if base_ref and head_ref:
            subprocess.run(["git", "fetch", "origin", f"{base_ref}:{base_ref}"],
                           capture_output=True, check=False)
            subprocess.run(["git", "fetch", "origin", f"{head_ref}:{head_ref}"],
                           capture_output=True, check=False)

            result = subprocess.run(
                ["git", "diff", "--name-only", f"origin/{base_ref}", "HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                console.print(f"  Detected {len(files)} changed file(s) via origin/{base_ref}..HEAD")
                return files

        # ── Strategy 2: three-dot diff with merge base ────────────────────────
        if base_ref:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                console.print(f"  Detected {len(files)} changed file(s) via ...HEAD diff")
                return files

        # ── Strategy 3: explicit merge-base ───────────────────────────────────
        for base in ["origin/main", "origin/master"]:
            result = subprocess.run(
                ["git", "merge-base", "HEAD", base],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                merge_base = result.stdout.strip()
                result2 = subprocess.run(
                    ["git", "diff", "--name-only", merge_base, "HEAD"],
                    capture_output=True, text=True, check=False
                )
                if result2.returncode == 0 and result2.stdout.strip():
                    files = [f.strip() for f in result2.stdout.strip().split("\n") if f.strip()]
                    console.print(f"  Detected {len(files)} changed file(s) via merge-base")
                    return files

        # ── Strategy 4: last commit diff ──────────────────────────────────────
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            console.print(f"  Detected {len(files)} changed file(s) via HEAD~1")
            return files

        console.print("  No files detected via any git strategy")

    except Exception as e:
        console.print(f"  Git diff error: {e}")

    return []


def _scan_directory(schema_path: str, workspace: str) -> list[str]:
    """Scan directory for all supported schema files."""
    results = []
    full_path = os.path.join(workspace, schema_path) if schema_path else workspace

    if not os.path.exists(full_path):
        console.print(f"  Schema path not found: {full_path}")
        return []

    for root, dirs, files in os.walk(full_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_PATTERNS]
        for file in files:
            _, ext = os.path.splitext(file)
            if ext in SUPPORTED_EXTENSIONS:
                abs_path = os.path.join(root, file)
                results.append(os.path.relpath(abs_path, workspace))
    return results


def _filter_files(files: list[str], schema_path: str) -> list[str]:
    """
    Filter files to only schema-relevant ones within schema_path.
    schema_path has already been normalized (no leading ./).
    """
    filtered = []
    for filepath in files:
        # Normalize the filepath too (remove ./ prefix if present)
        fp = filepath.lstrip("./") if filepath not in (".", "./") else filepath

        # Must be under schema_path (if schema_path is set)
        if schema_path and not fp.startswith(schema_path):
            continue

        # Must have a supported extension
        _, ext = os.path.splitext(fp)
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        # Must not match ignore patterns
        parts = fp.replace("\\", "/").split("/")
        if any(part in IGNORE_PATTERNS for part in parts):
            continue

        filtered.append(filepath)

    return filtered