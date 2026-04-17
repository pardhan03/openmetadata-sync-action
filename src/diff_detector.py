"""
diff_detector.py — Compares parsed file metadata against current OpenMetadata state.

Only generates update operations for fields that actually changed.
This prevents unnecessary API calls and noisy PR comments.
"""

from rich.console import Console
from openmetadata_client import OpenMetadataClient

console = Console()


class DiffDetector:
    """
    Computes the diff between what's in a schema file
    and what's currently stored in OpenMetadata.
    """

    def __init__(self, om_client: OpenMetadataClient):
        self.om_client = om_client

    def compute_diff(self, parsed: dict) -> list[dict]:
        """
        Compare parsed metadata from a file against the current state in OpenMetadata.

        Returns a list of diff objects, each describing one change:
          {
            "field":    "description",       # what changed
            "old":      "Old description",   # current value in OpenMetadata
            "new":      "New description",   # value from the schema file
          }

        Returns [] if nothing changed or table not found.
        """
        table_name = parsed["table_name"]
        current = self.om_client.get_current_metadata(table_name)
        diffs = []

        # ── Table-level fields ────────────────────────────────────────────────

        if self._has_changed(parsed.get("description"), current.get("description")):
            diffs.append({
                "field": "description",
                "old":   current.get("description", ""),
                "new":   parsed["description"],
            })

        if self._has_changed(parsed.get("owner"), current.get("owner")):
            if parsed.get("owner"):  # Only update owner if explicitly set
                diffs.append({
                    "field": "owner",
                    "old":   current.get("owner", ""),
                    "new":   parsed["owner"],
                })

        if self._tags_changed(parsed.get("tags", []), current.get("tags", [])):
            diffs.append({
                "field": "tags",
                "old":   current.get("tags", []),
                "new":   parsed["tags"],
            })

        # ── Column-level fields ───────────────────────────────────────────────

        current_cols = {c["name"]: c for c in current.get("columns", [])}

        for col in parsed.get("columns", []):
            col_name = col["name"]
            current_col = current_cols.get(col_name, {})

            # Column description
            if self._has_changed(col.get("description"), current_col.get("description")):
                if col.get("description"):  # Only update if we have a new value
                    diffs.append({
                        "field": f"column:{col_name}:description",
                        "old":   current_col.get("description", ""),
                        "new":   col["description"],
                    })

            # Column tags
            if self._tags_changed(col.get("tags", []), current_col.get("tags", [])):
                if col.get("tags"):
                    diffs.append({
                        "field": f"column:{col_name}:tags",
                        "old":   current_col.get("tags", []),
                        "new":   col["tags"],
                    })

        return diffs

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _has_changed(self, new_val, old_val) -> bool:
        """
        Check if a value has meaningfully changed.
        Treats None and "" as equivalent (both mean "not set").
        """
        new_clean = (new_val or "").strip()
        old_clean = (old_val or "").strip()
        return new_clean != old_clean

    def _tags_changed(self, new_tags: list, old_tags: list) -> bool:
        """
        Check if the tag list has changed.
        Order-insensitive comparison.
        """
        new_set = set(t.lower() for t in (new_tags or []))
        old_set = set(t.lower() for t in (old_tags or []))
        return new_set != old_set
