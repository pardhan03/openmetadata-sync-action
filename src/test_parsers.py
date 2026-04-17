"""
tests/test_parsers.py — Unit tests for all three schema parsers.

Run with:  pytest tests/ -v
"""

import sys
import os
import json
import tempfile
import pytest

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from parsers.dbt_parser import DBTParser
from parsers.sql_parser import SQLParser
from parsers.json_schema_parser import JSONSchemaParser


# ══════════════════════════════════════════════════════════
# DBT PARSER TESTS
# ══════════════════════════════════════════════════════════

class TestDBTParser:
    """Tests for the dbt YAML model parser."""

    def setup_method(self):
        self.parser = DBTParser()

    def _write_yaml(self, content: str) -> str:
        """Write YAML to a temp file and return its path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parses_basic_model(self):
        path = self._write_yaml("""
version: 2
models:
  - name: orders
    description: "All customer orders"
""")
        result = self.parser.parse(path)
        assert len(result) == 1
        assert result[0]["table_name"] == "orders"
        assert result[0]["description"] == "All customer orders"

    def test_parses_tags_and_owner(self):
        path = self._write_yaml("""
version: 2
models:
  - name: payments
    tags: [finance, PCI]
    meta:
      owner: "team@company.com"
""")
        result = self.parser.parse(path)
        assert result[0]["tags"] == ["finance", "PCI"]
        assert result[0]["owner"] == "team@company.com"

    def test_parses_columns(self):
        path = self._write_yaml("""
version: 2
models:
  - name: users
    columns:
      - name: user_id
        description: "Primary key"
        tags: [PK]
      - name: email
        description: "User email"
        tags: [PII]
""")
        result = self.parser.parse(path)
        cols = result[0]["columns"]
        assert len(cols) == 2
        assert cols[0]["name"] == "user_id"
        assert cols[0]["tags"] == ["PK"]
        assert cols[1]["name"] == "email"
        assert cols[1]["description"] == "User email"

    def test_parses_multiple_models(self):
        path = self._write_yaml("""
version: 2
models:
  - name: orders
    description: "Orders table"
  - name: customers
    description: "Customers table"
""")
        result = self.parser.parse(path)
        assert len(result) == 2

    def test_ignores_non_dbt_yaml(self):
        path = self._write_yaml("""
some_other_key: value
unrelated: data
""")
        result = self.parser.parse(path)
        assert result == []

    def test_source_type_is_dbt(self):
        path = self._write_yaml("""
version: 2
models:
  - name: orders
""")
        result = self.parser.parse(path)
        assert result[0]["source_type"] == "dbt"


# ══════════════════════════════════════════════════════════
# SQL PARSER TESTS
# ══════════════════════════════════════════════════════════

class TestSQLParser:
    """Tests for the SQL CREATE TABLE parser."""

    def setup_method(self):
        self.parser = SQLParser()

    def _write_sql(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parses_basic_create_table(self):
        path = self._write_sql("""
CREATE TABLE orders (
    order_id INT NOT NULL,
    amount DECIMAL(10,2)
);
""")
        result = self.parser.parse(path)
        assert len(result) == 1
        assert result[0]["table_name"] == "orders"

    def test_parses_file_level_comments(self):
        path = self._write_sql("""
-- description: All customer orders
-- owner: team@company.com
-- tags: finance, core
CREATE TABLE orders (order_id INT);
""")
        result = self.parser.parse(path)
        assert result[0]["description"] == "All customer orders"
        assert result[0]["owner"] == "team@company.com"
        assert "finance" in result[0]["tags"]
        assert "core" in result[0]["tags"]

    def test_parses_column_inline_comments(self):
        path = self._write_sql("""
CREATE TABLE users (
    user_id INT NOT NULL,  -- PK: Unique user identifier
    email VARCHAR(255)     -- PII: User email address
);
""")
        result = self.parser.parse(path)
        cols = {c["name"]: c for c in result[0]["columns"]}
        assert cols["user_id"]["description"] == "Unique user identifier"
        assert "PK" in cols["user_id"]["tags"]
        assert cols["email"]["description"] == "User email address"
        assert "PII" in cols["email"]["tags"]

    def test_parses_multiple_tables(self):
        path = self._write_sql("""
CREATE TABLE orders (id INT);
CREATE TABLE customers (id INT);
""")
        result = self.parser.parse(path)
        assert len(result) == 2

    def test_source_type_is_sql(self):
        path = self._write_sql("CREATE TABLE t (id INT);")
        result = self.parser.parse(path)
        assert result[0]["source_type"] == "sql"


# ══════════════════════════════════════════════════════════
# JSON SCHEMA PARSER TESTS
# ══════════════════════════════════════════════════════════

class TestJSONSchemaParser:
    """Tests for the JSON Schema parser."""

    def setup_method(self):
        self.parser = JSONSchemaParser()

    def _write_json(self, data: dict) -> str:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, f)
        f.close()
        return f.name

    def test_parses_standard_json_schema(self):
        path = self._write_json({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "orders",
            "description": "All customer orders",
            "x-owner": "team@company.com",
            "x-tags": ["finance"],
            "properties": {
                "order_id": {"type": "integer", "description": "Primary key"}
            }
        })
        result = self.parser.parse(path)
        assert len(result) == 1
        assert result[0]["table_name"] == "orders"
        assert result[0]["description"] == "All customer orders"
        assert result[0]["owner"] == "team@company.com"
        assert "finance" in result[0]["tags"]

    def test_parses_column_properties(self):
        path = self._write_json({
            "title": "users",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "User email",
                    "x-tags": ["PII"]
                }
            }
        })
        result = self.parser.parse(path)
        col = result[0]["columns"][0]
        assert col["name"] == "email"
        assert col["description"] == "User email"
        assert "PII" in col["tags"]

    def test_parses_custom_format(self):
        path = self._write_json({
            "table": "products",
            "description": "Product catalog",
            "owner": "catalog-team@company.com",
            "tags": ["inventory"],
            "columns": [
                {"name": "product_id", "type": "integer", "description": "PK"}
            ]
        })
        result = self.parser.parse(path)
        assert result[0]["table_name"] == "products"
        assert result[0]["description"] == "Product catalog"

    def test_handles_anyof_type(self):
        path = self._write_json({
            "title": "test_table",
            "properties": {
                "nullable_col": {"type": ["string", "null"]}
            }
        })
        result = self.parser.parse(path)
        col = result[0]["columns"][0]
        assert col["data_type"] == "VARCHAR"

    def test_ignores_non_schema_json(self):
        path = self._write_json({"random": "data", "no_schema": True})
        result = self.parser.parse(path)
        assert result == []

    def test_handles_invalid_json(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        f.write("{ this is not valid json }")
        f.close()
        result = self.parser.parse(f.name)
        assert result == []

    def test_source_type_is_json_schema(self):
        path = self._write_json({"title": "t", "properties": {}})
        result = self.parser.parse(path)
        assert result[0]["source_type"] == "json_schema"
