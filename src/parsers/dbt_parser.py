"""
dbt_parser.py — Parses dbt YAML model files and extracts metadata.

Supports dbt schema.yml files like:

  version: 2
  models:
    - name: orders
      description: "All customer orders"
      meta:
        owner: "data-team@company.com"
      tags: ["finance", "core"]
      columns:
        - name: order_id
          description: "Primary key"
          tags: ["PII"]
"""

import yaml
from rich.console import Console

console = Console()


class DBTParser:
    """
    Parses dbt v2 schema YAML files into a standard metadata format
    that the rest of the action can work with.
    """

    def parse(self, filepath: str) -> list[dict]:
        """
        Parse a dbt YAML file and return a list of table metadata dicts.
        Returns [] if the file is not a dbt schema file.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            console.print(f"  [red]Error reading {filepath}: {e}[/red]")
            return []

        # Only process files with 'version: 2' and 'models' key (dbt schema files)
        if not isinstance(data, dict):
            return []
        if "models" not in data:
            return []

        results = []
        for model in data.get("models", []):
            parsed = self._parse_model(model, filepath)
            if parsed:
                results.append(parsed)

        return results

    def _parse_model(self, model: dict, source_file: str) -> dict | None:
        """Extract metadata from a single dbt model definition."""
        if not isinstance(model, dict) or "name" not in model:
            return None

        table_name = model["name"]
        description = model.get("description", "")
        tags = self._normalize_tags(model.get("tags", []))
        owner = model.get("meta", {}).get("owner", "")

        # Parse columns
        columns = []
        for col in model.get("columns", []):
            if not isinstance(col, dict) or "name" not in col:
                continue
            columns.append({
                "name": col["name"],
                "description": col.get("description", ""),
                "tags": self._normalize_tags(col.get("tags", [])),
                "data_type": col.get("data_type", ""),  # optional in dbt
            })

        return {
            "table_name":   table_name,
            "description":  description,
            "tags":         tags,
            "owner":        owner,
            "columns":      columns,
            "source_file":  source_file,
            "source_type":  "dbt",
        }

    def _normalize_tags(self, tags) -> list[str]:
        """Ensure tags are always a clean list of strings."""
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if t]
        if isinstance(tags, str):
            return [tags.strip()] if tags.strip() else []
        return []
