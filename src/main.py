"""
main.py — Entry point for the OpenMetadata Sync GitHub Action

Flow:
  1. Read environment variables (set by action.yml from user inputs)
  2. Detect which files changed in this PR/push
  3. Parse those files to extract metadata
  4. Diff against current OpenMetadata state
  5. Push only what changed to OpenMetadata
  6. Post a summary comment on the PR
"""

import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from parsers.dbt_parser import DBTParser
from parsers.sql_parser import SQLParser
from parsers.json_schema_parser import JSONSchemaParser
from openmetadata_client import OpenMetadataClient
from diff_detector import DiffDetector
from pr_commenter import PRCommenter
from file_detector import detect_changed_files

console = Console()


def load_config() -> dict:
    """Load all configuration from environment variables."""
    config = {
        "om_host":          os.environ.get("OM_HOST", ""),
        "om_token":         os.environ.get("OM_TOKEN", ""),
        "github_token":     os.environ.get("GITHUB_TOKEN", ""),
        "schema_path":      os.environ.get("SCHEMA_PATH", "."),
        "db_service_name":  os.environ.get("DB_SERVICE_NAME", ""),
        "post_pr_comment":  os.environ.get("POST_PR_COMMENT", "true").lower() == "true",
        "dry_run":          os.environ.get("DRY_RUN", "false").lower() == "true",
        # GitHub context (automatically available inside GitHub Actions)
        "github_repo":      os.environ.get("GITHUB_REPOSITORY", ""),
        "github_pr_number": os.environ.get("PR_NUMBER", ""),
        "github_workspace": os.environ.get("GITHUB_WORKSPACE", "."),
    }

    # Validate required fields
    missing = [k for k in ["om_host", "om_token", "db_service_name"] if not config[k]]
    if missing:
        console.print(f"[red]❌ Missing required inputs: {', '.join(missing)}[/red]")
        sys.exit(1)

    return config


def parse_changed_files(changed_files: list[str], workspace: str) -> list[dict]:
    """
    Route each changed file to the correct parser.
    Returns a flat list of metadata objects extracted from all files.
    """
    all_metadata = []

    dbt_parser  = DBTParser()
    sql_parser  = SQLParser()
    json_parser = JSONSchemaParser()

    for filepath in changed_files:
        full_path = os.path.join(workspace, filepath)

        if not os.path.exists(full_path):
            console.print(f"[yellow]⚠ Skipping deleted file: {filepath}[/yellow]")
            continue

        # Route to correct parser based on file extension and content
        if filepath.endswith(".yml") or filepath.endswith(".yaml"):
            metadata = dbt_parser.parse(full_path)
        elif filepath.endswith(".sql"):
            metadata = sql_parser.parse(full_path)
        elif filepath.endswith(".json"):
            metadata = json_parser.parse(full_path)
        else:
            console.print(f"[dim]Skipping unsupported file type: {filepath}[/dim]")
            continue

        if metadata:
            console.print(f"[green]✓ Parsed:[/green] {filepath} → {len(metadata)} table(s) found")
            all_metadata.extend(metadata)

    return all_metadata


def main():
    console.print(Panel.fit(
        "[bold blue]OpenMetadata Sync Action[/bold blue]\n"
        "Syncing schema changes to your data catalog...",
        border_style="blue"
    ))

    # ── 1. Load config ────────────────────────────────────────────────────────
    config = load_config()

    if config["dry_run"]:
        console.print("[yellow]🔍 DRY RUN MODE — No changes will be written to OpenMetadata[/yellow]\n")

    # ── 2. Detect changed files ───────────────────────────────────────────────
    console.print("[bold]Step 1:[/bold] Detecting changed schema files...")
    changed_files = detect_changed_files(config["schema_path"], config["github_workspace"])

    if not changed_files:
        console.print("[green]✅ No schema files changed. Nothing to sync.[/green]")
        # Set GitHub Action outputs
        print("tables_updated=0")
        print("columns_updated=0")
        print("changes_detected=false")
        sys.exit(0)

    console.print(f"  Found [bold]{len(changed_files)}[/bold] changed file(s):\n")
    for f in changed_files:
        console.print(f"  • {f}")

    # ── 3. Parse files ────────────────────────────────────────────────────────
    console.print("\n[bold]Step 2:[/bold] Parsing metadata from changed files...")
    parsed_metadata = parse_changed_files(changed_files, config["github_workspace"])

    if not parsed_metadata:
        console.print("[yellow]⚠ Files changed but no parseable metadata found.[/yellow]")
        sys.exit(0)

    # ── 4. Connect to OpenMetadata ────────────────────────────────────────────
    console.print("\n[bold]Step 3:[/bold] Connecting to OpenMetadata...")
    om_client = OpenMetadataClient(
        host=config["om_host"],
        token=config["om_token"],
        service_name=config["db_service_name"]
    )

    if not om_client.health_check():
        console.print("[red]❌ Cannot connect to OpenMetadata. Check OM_HOST and OM_TOKEN.[/red]")
        sys.exit(1)

    console.print(f"  [green]✓ Connected to:[/green] {config['om_host']}")

    # ── 5. Diff & Push ────────────────────────────────────────────────────────
    console.print("\n[bold]Step 4:[/bold] Comparing with current OpenMetadata state...")
    diff_detector = DiffDetector(om_client)
    tables_updated = 0
    columns_updated = 0
    change_summary = []  # Used for PR comment

    for table_meta in parsed_metadata:
        diffs = diff_detector.compute_diff(table_meta)

        if not diffs:
            console.print(f"  [dim]No changes for table:[/dim] {table_meta['table_name']}")
            continue

        console.print(f"  [cyan]Changes detected for:[/cyan] {table_meta['table_name']}")
        for diff in diffs:
            console.print(f"    → {diff['field']}: [red]{diff['old']}[/red] → [green]{diff['new']}[/green]")

        if not config["dry_run"]:
            result = om_client.update_table(table_meta, diffs)
            tables_updated += 1
            columns_updated += result.get("columns_updated", 0)

        change_summary.append({
            "table": table_meta["table_name"],
            "diffs": diffs
        })

    # ── 6. Print summary ──────────────────────────────────────────────────────
    console.print("\n")
    summary_table = Table(title="Sync Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_row("Tables Updated", str(tables_updated))
    summary_table.add_row("Columns Updated", str(columns_updated))
    summary_table.add_row("Dry Run", "Yes" if config["dry_run"] else "No")
    console.print(summary_table)

    # ── 7. Post PR comment ────────────────────────────────────────────────────
    if config["post_pr_comment"] and config["github_pr_number"] and change_summary:
        console.print("\n[bold]Step 5:[/bold] Posting PR summary comment...")
        commenter = PRCommenter(
            github_token=config["github_token"],
            repo_name=config["github_repo"],
            pr_number=int(config["github_pr_number"])
        )
        commenter.post_summary(change_summary, tables_updated, columns_updated, config["dry_run"])
        console.print("  [green]✓ PR comment posted![/green]")

    # ── 8. Set GitHub Action outputs ──────────────────────────────────────────
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"tables_updated={tables_updated}\n")
        f.write(f"columns_updated={columns_updated}\n")
        f.write(f"changes_detected={'true' if change_summary else 'false'}\n")

    console.print("\n[bold green]✅ OpenMetadata sync complete![/bold green]")


if __name__ == "__main__":
    main()
