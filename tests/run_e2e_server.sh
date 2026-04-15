#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$ROOT_DIR/tests/.tmp"
DATA_DIR="$TMP_DIR/e2e-data"
WORKSPACE_DIR="$TMP_DIR/workspace"

rm -rf "$DATA_DIR" "$WORKSPACE_DIR"
mkdir -p "$DATA_DIR" "$WORKSPACE_DIR"

export PMT_DATA_DIR="$DATA_DIR"
export PMT_PROJECTS_DIR="$DATA_DIR/projects"
export PMT_MASTER_DB="$DATA_DIR/master.db"
export APP_RUN_PORT=5011
export PYTHONUNBUFFERED=1

exec "$ROOT_DIR/run.sh"
