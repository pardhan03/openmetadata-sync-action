"""
pr_commenter.py — Posts a formatted summary comment on the GitHub Pull Request.

The comment shows exactly what metadata was synced to OpenMetadata,
making the PR self-documenting for reviewers.
"""

from github import Github
from rich.console import Console

console = Console()

# Emoji indicators for different field types
FIELD_ICONS = {
    "description": "📝",
    "owner":       "👤",
    "tags":        "🏷️",
    "column":      "📊",
}


class PRCommenter:
    """Posts a Markdown summary comment on a GitHub Pull Request."""

    def __init__(self, github_token: str, repo_name: str, pr_number: int):
        self.gh = Github(github_token)
        self.repo = self.gh.get_repo(repo_name)
        self.pr = self.repo.get_pull(pr_number)

    def post_summary(
        self,
        change_summary: list[dict],
        tables_updated: int,
        columns_updated: int,
        dry_run: bool = False
    ) -> None:
        """
        Build and post a Markdown comment summarizing all metadata changes.
        If a previous comment from this action exists, it replaces it.
        """
        body = self._build_comment(change_summary, tables_updated, columns_updated, dry_run)

        # Delete previous comment from this action (keep PRs clean)
        self._delete_previous_comment()

        self.pr.create_issue_comment(body)

    def _build_comment(
        self,
        change_summary: list[dict],
        tables_updated: int,
        columns_updated: int,
        dry_run: bool
    ) -> str:
        """Build the full Markdown comment body."""
        lines = []

        # Header
        mode_badge = "🔍 **DRY RUN** — " if dry_run else ""
        lines.append(f"## {mode_badge}🗄️ OpenMetadata Sync Summary")
        lines.append("")

        if not change_summary:
            lines.append("✅ No metadata changes detected in this PR.")
            lines.append("")
            lines.append("---")
            lines.append("*Powered by [OpenMetadata Sync Action](https://github.com)*")
            return "\n".join(lines)

        # Stats row
        action_word = "Would update" if dry_run else "Updated"
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| {action_word} tables | **{tables_updated}** |")
        lines.append(f"| {action_word} columns | **{columns_updated}** |")
        lines.append(f"| Total changes | **{sum(len(s['diffs']) for s in change_summary)}** |")
        lines.append("")

        # Per-table breakdown
        lines.append("### Changes by Table")
        lines.append("")

        for entry in change_summary:
            table = entry["table"]
            diffs = entry["diffs"]

            lines.append(f"<details>")
            lines.append(f"<summary><strong>📋 {table}</strong> ({len(diffs)} change(s))</summary>")
            lines.append("")
            lines.append("| Field | Before | After |")
            lines.append("|-------|--------|-------|")

            for diff in diffs:
                field = diff["field"]
                old_val = self._format_value(diff["old"])
                new_val = self._format_value(diff["new"])
                icon = self._get_icon(field)
                display_field = self._format_field_name(field)

                lines.append(f"| {icon} `{display_field}` | {old_val} | {new_val} |")

            lines.append("")
            lines.append("</details>")
            lines.append("")

        # Footer
        lines.append("---")
        if dry_run:
            lines.append("⚠️ *This was a dry run. No changes were written to OpenMetadata.*")
        else:
            lines.append("✅ *Changes have been applied to OpenMetadata.*")
        lines.append("")
        lines.append("*Powered by [OpenMetadata Sync Action](https://github.com) 🤖*")

        return "\n".join(lines)

    def _delete_previous_comment(self) -> None:
        """Remove any previous comment left by this action to avoid clutter."""
        try:
            for comment in self.pr.get_issue_comments():
                if "OpenMetadata Sync Summary" in comment.body:
                    comment.delete()
                    break
        except Exception:
            pass  # Non-critical — it's fine if we can't delete old comments

    def _format_value(self, val) -> str:
        """Format a value for display in a Markdown table cell."""
        if isinstance(val, list):
            if not val:
                return "*none*"
            return ", ".join(f"`{t}`" for t in val)
        if not val:
            return "*empty*"
        # Truncate long strings
        s = str(val)
        if len(s) > 60:
            s = s[:57] + "..."
        return s

    def _get_icon(self, field: str) -> str:
        """Return an emoji icon for a field type."""
        if field.startswith("column:"):
            return FIELD_ICONS["column"]
        return FIELD_ICONS.get(field, "🔧")

    def _format_field_name(self, field: str) -> str:
        """Make a field key human-readable."""
        if field.startswith("column:"):
            parts = field.split(":")
            return f"{parts[1]}.{parts[2]}"  # e.g. "customer_id.description"
        return field
