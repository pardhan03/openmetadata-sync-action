"""
sql_parser.py — Parses SQL CREATE TABLE statements and extracts metadata.

Supports files like:

  -- description: All customer orders
  -- owner: data-team@company.com
  -- tags: finance, core
  CREATE TABLE orders (
      order_id    INT       NOT NULL,  -- Primary key
      customer_id INT       NOT NULL,  -- PII: Customer identifier
      amount      DECIMAL(10,2),
      created_at  TIMESTAMP
  );
"""

import re
import sqlglot
from sqlglot import exp
from rich.console import Console

console = Console()


class SQLParser:
    """
    Parses SQL files to extract table name, columns, data types,
    and metadata encoded in SQL comments.
    """

    def parse(self, filepath: str) -> list[dict]:
        """
        Parse a SQL file and return a list of table metadata dicts.
        A single SQL file can contain multiple CREATE TABLE statements.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            console.print(f"  [red]Error reading {filepath}: {e}[/red]")
            return []

        if not content.strip():
            return []

        results = []

        # Extract file-level metadata from top-of-file comments
        file_meta = self._extract_file_comments(content)

        # Parse SQL using sqlglot
        try:
            statements = sqlglot.parse(content, error_level=sqlglot.ErrorLevel.WARN)
        except Exception as e:
            console.print(f"  [yellow]SQL parse warning for {filepath}: {e}[/yellow]")
            return []

        for statement in statements:
            if not isinstance(statement, exp.Create):
                continue
            if statement.kind != "TABLE":
                continue

            parsed = self._parse_create_table(statement, content, file_meta, filepath)
            if parsed:
                results.append(parsed)

        return results

    def _parse_create_table(
        self, statement: exp.Create, raw_sql: str, file_meta: dict, source_file: str
    ) -> dict | None:
        """Extract metadata from a single CREATE TABLE statement."""
        try:
            table_name = statement.find(exp.Table).name
        except AttributeError:
            return None

        columns = []
        for col_def in statement.find_all(exp.ColumnDef):
            col_name = col_def.name
            data_type = col_def.args.get("kind")
            data_type_str = str(data_type).upper() if data_type else ""

            # Extract inline comment for this column (e.g. "-- PII: description")
            col_description, col_tags = self._extract_inline_column_comment(raw_sql, col_name)

            columns.append({
                "name":        col_name,
                "description": col_description,
                "tags":        col_tags,
                "data_type":   data_type_str,
            })

        return {
            "table_name":  table_name,
            "description": file_meta.get("description", ""),
            "tags":        file_meta.get("tags", []),
            "owner":       file_meta.get("owner", ""),
            "columns":     columns,
            "source_file": source_file,
            "source_type": "sql",
        }

    def _extract_file_comments(self, sql: str) -> dict:
        """
        Extract metadata from structured comments at the top of the SQL file.

        Supports:
          -- description: Some table description
          -- owner: team@company.com
          -- tags: tag1, tag2
        """
        meta = {"description": "", "owner": "", "tags": []}

        desc_match = re.search(r"--\s*description:\s*(.+)", sql, re.IGNORECASE)
        if desc_match:
            meta["description"] = desc_match.group(1).strip()

        owner_match = re.search(r"--\s*owner:\s*(.+)", sql, re.IGNORECASE)
        if owner_match:
            meta["owner"] = owner_match.group(1).strip()

        tags_match = re.search(r"--\s*tags:\s*(.+)", sql, re.IGNORECASE)
        if tags_match:
            raw_tags = tags_match.group(1).strip()
            meta["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]

        return meta

    def _extract_inline_column_comment(self, sql: str, col_name: str) -> tuple[str, list[str]]:
        """
        Look for an inline comment on the same line as a column definition.

        Example:
          customer_id INT NOT NULL,  -- PII: Unique customer identifier
          ↑ extracts description="Unique customer identifier", tags=["PII"]
        """
        # Match the column name followed by anything and then a comment
        pattern = rf"\b{re.escape(col_name)}\b[^,\n]*--\s*(.+)"
        match = re.search(pattern, sql, re.IGNORECASE)

        if not match:
            return "", []

        comment = match.group(1).strip()

        # Check for "TAG: description" format
        tag_prefix_match = re.match(r"^([A-Z_]+):\s*(.+)$", comment, re.IGNORECASE)
        if tag_prefix_match:
            tag = tag_prefix_match.group(1).upper()
            description = tag_prefix_match.group(2).strip()
            return description, [tag]

        return comment, []
