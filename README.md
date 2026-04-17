# 🗄️ OpenMetadata Sync — GitHub Action

> Automatically sync metadata from your schema files to OpenMetadata on every Pull Request.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenMetadata](https://img.shields.io/badge/OpenMetadata-1.6-blue)](https://open-metadata.org)

---

## The Problem

Every time a developer updates a dbt model, SQL schema, or JSON schema file, someone has to manually update the data catalog in OpenMetadata. This never happens consistently, leading to a stale, unreliable catalog.

## The Solution

This GitHub Action **automatically syncs metadata** from your schema files to OpenMetadata every time a PR is opened or updated. Zero manual effort. Always up to date.

```
Developer updates orders.yml in a PR
           ↓
GitHub Action triggers automatically
           ↓
Parses changed schema files
           ↓
Diffs against current OpenMetadata state
           ↓
Pushes only what changed via REST API
           ↓
Posts a summary comment on the PR ✅
```

---

## Supported File Types

| Format | Example | What's Extracted |
|--------|---------|-----------------|
| **dbt YAML** | `models/orders.yml` | descriptions, tags, owners, column metadata |
| **SQL** | `schema/orders.sql` | table name, columns, types, comment-based metadata |
| **JSON Schema** | `schemas/orders.json` | all standard JSON Schema fields + `x-owner`, `x-tags` |

---

## Quick Start

### Step 1 — Add secrets to your GitHub repo

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `OPENMETADATA_HOST` | Your OpenMetadata URL e.g. `http://your-server:8585` |
| `OPENMETADATA_TOKEN` | JWT token from OpenMetadata Settings → Bots |
| `OM_SERVICE_NAME` | The Database Service name in OpenMetadata |

### Step 2 — Add the workflow file

Create `.github/workflows/openmetadata-sync.yml` in your repo:

```yaml
name: Sync Metadata to OpenMetadata

on:
  pull_request:
    paths: ['**.yml', '**.yaml', '**.sql', '**.json']

jobs:
  sync-metadata:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: your-username/openmetadata-sync-action@v1
        with:
          openmetadata_host: ${{ secrets.OPENMETADATA_HOST }}
          openmetadata_token: ${{ secrets.OPENMETADATA_TOKEN }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          database_service_name: ${{ secrets.OM_SERVICE_NAME }}
          schema_path: './models'
```

That's it. Open a PR and watch it work. 🎉

---

## File Format Examples

### dbt YAML (`models/orders.yml`)
```yaml
version: 2
models:
  - name: orders
    description: "All customer orders"
    meta:
      owner: "data-team@company.com"
    tags: [finance, core]
    columns:
      - name: customer_id
        description: "Customer identifier"
        tags: [PII]
```

### SQL (`schema/orders.sql`)
```sql
-- description: All customer orders
-- owner: data-team@company.com
-- tags: finance, core
CREATE TABLE orders (
    order_id    INT  NOT NULL,   -- PK: Primary key
    customer_id INT  NOT NULL    -- PII: Customer identifier
);
```

### JSON Schema (`schemas/orders.json`)
```json
{
  "title": "orders",
  "description": "All customer orders",
  "x-owner": "data-team@company.com",
  "x-tags": ["finance"],
  "properties": {
    "customer_id": {
      "type": "integer",
      "description": "Customer identifier",
      "x-tags": ["PII"]
    }
  }
}
```

---

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `openmetadata_host` | ✅ | — | OpenMetadata instance URL |
| `openmetadata_token` | ✅ | — | JWT API token |
| `github_token` | ✅ | — | Use `secrets.GITHUB_TOKEN` |
| `database_service_name` | ✅ | — | Service name in OpenMetadata |
| `schema_path` | ❌ | `.` | Path to schema files |
| `post_pr_comment` | ❌ | `true` | Post PR summary comment |
| `dry_run` | ❌ | `false` | Log changes without applying |

## Outputs

| Output | Description |
|--------|-------------|
| `tables_updated` | Number of tables updated |
| `columns_updated` | Number of columns updated |
| `changes_detected` | `true` if any changes were found |

---

## Local Development & Testing

```bash
# Clone the repo
git clone https://github.com/your-username/openmetadata-sync-action
cd openmetadata-sync-action

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Test locally with dry run
export OM_HOST="http://localhost:8585"
export OM_TOKEN="your-token"
export DB_SERVICE_NAME="your-service"
export SCHEMA_PATH="./examples/dbt_project/models"
export DRY_RUN="true"
export GITHUB_WORKSPACE="."
python src/main.py
```

---

## Architecture

```
openmetadata-sync-action/
├── action.yml                    # GitHub Action definition
├── Dockerfile                    # Container for the action
├── requirements.txt
├── src/
│   ├── main.py                   # Entry point & orchestration
│   ├── file_detector.py          # Detect changed files via git diff
│   ├── openmetadata_client.py    # OpenMetadata REST API wrapper
│   ├── diff_detector.py          # Smart change detection
│   ├── pr_commenter.py           # GitHub PR comment poster
│   └── parsers/
│       ├── dbt_parser.py         # dbt YAML model parser
│       ├── sql_parser.py         # SQL CREATE TABLE parser
│       └── json_schema_parser.py # JSON Schema parser
├── tests/
│   └── test_parsers.py
└── examples/
    ├── dbt_project/models/schema.yml
    ├── sql_project/products.sql
    └── json_project/payments.json
```

---

## Setting Up OpenMetadata Locally

```bash
# Download the docker-compose file
curl -sL https://github.com/open-metadata/OpenMetadata/releases/download/1.6.0-release/docker-compose.yml -o docker-compose.yml

# Start OpenMetadata
docker compose up -d

# Access at http://localhost:8585
# Default credentials: admin / admin
```

Get your API token: **Settings → Bots → ingestion-bot → Token**

---

## License

MIT © Your Name

Built for the [OpenMetadata Hackathon](https://openmetadata.org) 🏆
