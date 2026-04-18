"""
openmetadata_client.py — Handles all communication with the OpenMetadata REST API.

Responsibilities:
  - Authenticate using a JWT token
  - Find tables by name inside a database service
  - Update table descriptions, tags, and owners
  - Update column descriptions, tags, and types
"""

import requests
from rich.console import Console

console = Console()


class OpenMetadataClient:
    """
    Lightweight wrapper around the OpenMetadata REST API.
    Uses requests directly for maximum transparency and control.
    """

    def __init__(self, host: str, token: str, service_name: str):
        self.host = host.rstrip("/")
        self.service_name = service_name
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        })

    # ── Health ─────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Ping OpenMetadata to verify connectivity and auth."""
        try:
            resp = self.session.get(f"{self.host}/api/v1/system/status", timeout=10)
            return resp.status_code == 200
        except Exception as e:
            console.print(f"  [red]Health check failed: {e}[/red]")
            return False

    # ── Table Lookup ──────────────────────────────────────────────────────────

    def get_table(self, table_name: str) -> dict | None:
        """
        Look up a table in OpenMetadata by name within the configured service.

        Strategy (in order):
          1. Search API  — fast, works on all OM versions, no 400 errors
          2. FQN lookup  — direct fetch if we can construct the FQN
          3. List API    — last resort fallback
        """
        # ── 1. Search API (primary) ───────────────────────────────────────────
        result = self._search_table_by_name(table_name)
        if result:
            return result

        # ── 2. Try constructing FQN directly ─────────────────────────────────
        # Common OM FQN patterns: service.db.schema.table or service.db.table
        for fqn_pattern in [
            f"{self.service_name}.default.public.{table_name}",
            f"{self.service_name}.default.{table_name}",
            f"{self.service_name}.{table_name}",
        ]:
            result = self._get_table_by_fqn(fqn_pattern)
            if result:
                return result

        # ── 3. List API fallback (may 400 on some OM versions) ────────────────
        try:
            resp = self.session.get(
                f"{self.host}/api/v1/tables",
                params={
                    "fields": "columns,tags,owner,description",
                    "limit": 20,
                    "service": self.service_name,  # filter by service to avoid 400
                },
                timeout=10
            )
            if resp.status_code == 200:
                for table in resp.json().get("data", []):
                    if table.get("name") == table_name:
                        return table
        except Exception:
            pass

        return None

    def _search_table_by_name(self, table_name: str) -> dict | None:
        """Use the OpenMetadata search API to find a table by name."""
        try:
            resp = self.session.get(
                f"{self.host}/api/v1/search/query",
                params={
                    "q": table_name,
                    "index": "table_search_index",
                    "from": 0,
                    "size": 5,
                },
                timeout=10
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])

            for hit in hits:
                source = hit.get("_source", {})
                if source.get("name") == table_name and self.service_name in source.get("fullyQualifiedName", ""):
                    # Fetch full table entity
                    fqn = source["fullyQualifiedName"]
                    return self._get_table_by_fqn(fqn)

        except Exception as e:
            console.print(f"  [dim]Search fallback failed for '{table_name}': {e}[/dim]")

        return None

    def _get_table_by_fqn(self, fqn: str) -> dict | None:
        """Fetch a complete table entity by its Fully Qualified Name."""
        try:
            resp = self.session.get(
                f"{self.host}/api/v1/tables/name/{fqn}",
                params={"fields": "columns,tags,owner,description"},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            console.print(f"  [dim]FQN lookup failed: {e}[/dim]")
        return None

    # ── Table Update ──────────────────────────────────────────────────────────

    def update_table(self, table_meta: dict, diffs: list[dict]) -> dict:
        """
        Apply metadata changes to a table in OpenMetadata.
        Uses PATCH with JSON Patch operations for precise updates.

        Returns a dict with counts of what was updated.
        """
        table_name = table_meta["table_name"]
        existing = self.get_table(table_name)

        if not existing:
            console.print(f"  [yellow]Table '{table_name}' not found in OpenMetadata. Skipping.[/yellow]")
            return {"columns_updated": 0}

        table_id = existing["id"]
        patch_ops = []
        columns_updated = 0

        for diff in diffs:
            field = diff["field"]
            new_val = diff["new"]

            if field == "description":
                patch_ops.append({
                    "op": "replace" if existing.get("description") else "add",
                    "path": "/description",
                    "value": new_val
                })

            elif field == "owner":
                patch_ops.extend(self._build_owner_patch(new_val, existing))

            elif field == "tags":
                patch_ops.extend(self._build_tags_patch(new_val))

            elif field.startswith("column:"):
                col_patch = self._build_column_patch(field, new_val, existing)
                patch_ops.extend(col_patch)
                columns_updated += 1

        if not patch_ops:
            return {"columns_updated": 0}

        try:
            resp = self.session.patch(
                f"{self.host}/api/v1/tables/{table_id}",
                json=patch_ops,
                headers={"Content-Type": "application/json-patch+json"},
                timeout=15
            )
            resp.raise_for_status()
            console.print(f"  [green]✓ Updated table:[/green] {table_name}")
        except Exception as e:
            console.print(f"  [red]Failed to update '{table_name}': {e}[/red]")

        return {"columns_updated": columns_updated}

    # ── Patch Builders ────────────────────────────────────────────────────────

    def _build_owner_patch(self, owner_email: str, existing: dict) -> list[dict]:
        """Build a JSON Patch operation to set the table owner."""
        if not owner_email:
            return []
        return [{
            "op": "replace" if existing.get("owner") else "add",
            "path": "/owner",
            "value": {
                "type": "user",
                "name": owner_email
            }
        }]

    def _build_tags_patch(self, tags: list[str]) -> list[dict]:
        """Build JSON Patch operations to set table-level tags."""
        if not tags:
            return []
        tag_values = [
            {"tagFQN": f"Classification.{tag}", "source": "Classification", "labelType": "Manual"}
            for tag in tags
        ]
        return [{"op": "replace", "path": "/tags", "value": tag_values}]

    def _build_column_patch(self, field: str, new_val, existing: dict) -> list[dict]:
        """
        Build JSON Patch operations to update a specific column.
        field format: "column:column_name:description" or "column:column_name:tags"
        """
        try:
            _, col_name, col_field = field.split(":", 2)
        except ValueError:
            return []

        # Find column index in existing table
        columns = existing.get("columns", [])
        col_index = next(
            (i for i, c in enumerate(columns) if c.get("name") == col_name),
            None
        )

        if col_index is None:
            return []

        if col_field == "description":
            return [{
                "op": "replace",
                "path": f"/columns/{col_index}/description",
                "value": new_val
            }]

        if col_field == "tags":
            tag_values = [
                {"tagFQN": f"Classification.{tag}", "source": "Classification", "labelType": "Manual"}
                for tag in new_val
            ]
            return [{
                "op": "replace",
                "path": f"/columns/{col_index}/tags",
                "value": tag_values
            }]

        return []

    # ── Read Helpers ──────────────────────────────────────────────────────────

    def get_current_metadata(self, table_name: str) -> dict:
        """
        Get the current metadata for a table in a normalized format
        (same structure as what our parsers return).
        Returns empty structure if table not found.
        """
        table = self.get_table(table_name)

        if not table:
            return {
                "table_name": table_name,
                "description": "",
                "tags": [],
                "owner": "",
                "columns": [],
            }

        # Normalize tags
        tags = [t.get("tagFQN", "").split(".")[-1] for t in table.get("tags", [])]
        owner = table.get("owner", {}).get("name", "") if table.get("owner") else ""

        columns = []
        for col in table.get("columns", []):
            col_tags = [t.get("tagFQN", "").split(".")[-1] for t in col.get("tags", [])]
            columns.append({
                "name":        col.get("name", ""),
                "description": col.get("description", ""),
                "tags":        col_tags,
                "data_type":   col.get("dataType", ""),
            })

        return {
            "table_name":  table_name,
            "description": table.get("description", ""),
            "tags":        tags,
            "owner":       owner,
            "columns":     columns,
        }