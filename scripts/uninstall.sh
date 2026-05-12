#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_NAME="${HERMES_PLUGIN_NAME:-hermes-smart-router}"
TARGET_DIR="$HERMES_HOME/plugins/$PLUGIN_NAME"
REGISTRY_FILE="$HERMES_HOME/plugins/registry.yaml"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Plugin not installed: $TARGET_DIR"
  exit 0
fi

rm -rf "$TARGET_DIR"

if [[ -f "$REGISTRY_FILE" ]]; then
  # Remove the matching 3-line block if present.
  awk -v name="$PLUGIN_NAME" '
    $0 ~ "name: "name {skip=3}
    skip>0 {skip--; next}
    {print}
  ' "$REGISTRY_FILE" >"$REGISTRY_FILE.tmp" && mv "$REGISTRY_FILE.tmp" "$REGISTRY_FILE"
fi

echo "Uninstalled $PLUGIN_NAME from $TARGET_DIR"
