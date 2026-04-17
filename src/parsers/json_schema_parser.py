"""
json_schema_parser.py — Parses JSON Schema files and extracts table metadata.

Supports two formats:

Format 1 — Standard JSON Schema:
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "orders",
    "description": "All customer orders",
    "x-owner": "data-team@company.com",
    "x-tags": ["finance"],
    "properties": {
      "order_id": {
        "type": "integer",
        "description": "Primary key",
        "x-tags": ["PK"]
      }
    }
  }

Format 2 — Custom metadata schema (simpler):
  {
    "table": "orders",
    "description": "All customer orders",
    "owner": "data-team@company.com",
    "tags": ["finance"],
    "columns": [
      { "name": "order_id", "type": "integer", "description": "Primary key" }
    ]
  }
"""

import json
from rich.console import Console

console = Console()

# JSON types → SQL-like type names for OpenMetadata
JSON_TYPE_MAP = {
    "integer": "INT",
    "number":  "FLOAT",
    "string":  "VARCHAR",
    "boolean": "BOOLEAN",
    "array":   "ARRAY",
    "object":  "JSON",
    "null":    "NULL",
}


class JSONSchemaParser:
    """
    Parses JSON Schema files into the standard metadata format.
    Auto-detects between standard JSON Schema and custom metadata format.
    """

    def parse(self, filepath: str) -> list[dict]:
        """
        Parse a JSON file and return a list of table metadata dicts.
        Returns [] if not a recognizable schema file.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"  [yellow]Skipping {filepath}: not valid JSON ({e})[/yellow]")
            return []
        except Exception as e:
            console.print(f"  [red]Error reading {filepath}: {e}[/red]")
            return []

        if not isinstance(data, dict):
            return []

        # Detect which format and route accordingly
        if "properties" in data or "$schema" in data:
            result = self._parse_json_schema_format(data, filepath)
        elif "columns" in data or "table" in data:
            result = self._parse_custom_format(data, filepath)
        else:
            console.print(f"  [dim]Skipping {filepath}: no recognizable schema structure[/dim]")
            return []

        return [result] if result else []

    def _parse_json_schema_format(self, data: dict, source_file: str) -> dict | None:
        """Parse a standard JSON Schema (draft-07/draft-2020) file."""
        table_name = (
            data.get("title") or
            data.get("$id", "").split("/")[-1].replace(".json", "") or
            source_file.split("/")[-1].replace(".json", "")
        )

        if not table_name:
            return None

        description = data.get("description", "")
        owner = data.get("x-owner", "")
        tags = self._normalize_tags(data.get("x-tags", []))

        columns = []
        for col_name, col_def in data.get("properties", {}).items():
            if not isinstance(col_def, dict):
                continue

            # Handle anyOf / oneOf / allOf type definitions
            col_type = col_def.get("type", "")
            if isinstance(col_type, list):
                # e.g. ["string", "null"] → take first non-null
                col_type = next((t for t in col_type if t != "null"), "string")

            columns.append({
                "name":        col_name,
                "description": col_def.get("description", ""),
                "tags":        self._normalize_tags(col_def.get("x-tags", [])),
                "data_type":   JSON_TYPE_MAP.get(col_type.lower(), col_type.upper()),
            })

        return {
            "table_name":  table_name,
            "description": description,
            "tags":        tags,
            "owner":       owner,
            "columns":     columns,
            "source_file": source_file,
            "source_type": "json_schema",
        }

    def _parse_custom_format(self, data: dict, source_file: str) -> dict | None:
        """Parse a custom/simplified metadata JSON format."""
        table_name = (
            data.get("table") or
            data.get("name") or
            source_file.split("/")[-1].replace(".json", "")
        )

        if not table_name:
            return None

        description = data.get("description", "")
        owner = data.get("owner", "")
        tags = self._normalize_tags(data.get("tags", []))

        columns = []
        for col in data.get("columns", []):
            if not isinstance(col, dict) or "name" not in col:
                continue

            raw_type = col.get("type", "")
            columns.append({
                "name":        col["name"],
                "description": col.get("description", ""),
                "tags":        self._normalize_tags(col.get("tags", [])),
                "data_type":   JSON_TYPE_MAP.get(raw_type.lower(), raw_type.upper()),
            })

        return {
            "table_name":  table_name,
            "description": description,
            "tags":        tags,
            "owner":       owner,
            "columns":     columns,
            "source_file": source_file,
            "source_type": "json_schema",
        }

    def _normalize_tags(self, tags) -> list[str]:
        """Ensure tags are always a clean list of strings."""
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if t]
        if isinstance(tags, str):
            return [tags.strip()] if tags.strip() else []
        return []
