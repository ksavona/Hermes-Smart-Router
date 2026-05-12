#!/usr/bin/env bash
set -euo pipefail

# You can override these at install time:
# HERMES_PLUGIN_REPO_URL, HERMES_PLUGIN_BRANCH, HERMES_HOME, HERMES_PLUGIN_NAME
REPO_URL="${HERMES_PLUGIN_REPO_URL:-https://github.com/ksavona/Hermes-Smart-Router.git}"
BRANCH="${HERMES_PLUGIN_BRANCH:-main}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_NAME="${HERMES_PLUGIN_NAME:-hermes-smart-router}"

TARGET_DIR="$HERMES_HOME/plugins/$PLUGIN_NAME"
TMP_DIR="$(mktemp -d)"
CONFIG_FILE="$HERMES_HOME/config.yaml"
REGISTRY_FILE="$HERMES_HOME/plugins/registry.yaml"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is required but not installed."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but not installed."
  exit 1
fi

echo "Installing $PLUGIN_NAME into $TARGET_DIR"
mkdir -p "$HERMES_HOME/plugins"

git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR/repo"

rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -R "$TMP_DIR/repo/." "$TARGET_DIR/"

echo "Installing Python package"
python3 -m pip install --user "$TARGET_DIR"

mkdir -p "$(dirname "$REGISTRY_FILE")"

if [[ ! -f "$REGISTRY_FILE" ]]; then
  cat >"$REGISTRY_FILE" <<EOF
plugins:
  - name: $PLUGIN_NAME
    path: $TARGET_DIR
    entrypoint: hermes_plugin_starter.plugin:register
EOF
else
  if ! grep -q "name: $PLUGIN_NAME" "$REGISTRY_FILE"; then
    cat >>"$REGISTRY_FILE" <<EOF
  - name: $PLUGIN_NAME
    path: $TARGET_DIR
    entrypoint: hermes_plugin_starter.plugin:register
EOF
  fi
fi

if [[ -f "$CONFIG_FILE" ]] && ! grep -q "plugins_registry:" "$CONFIG_FILE"; then
  cat >>"$CONFIG_FILE" <<EOF

plugins_registry: $REGISTRY_FILE
EOF
fi

echo "Running Hermes Smart Router setup"
python3 -m hermes_plugin_starter setup
python3 -m hermes_plugin_starter doctor

echo "Installed $PLUGIN_NAME successfully."
echo "Plugin path: $TARGET_DIR"
echo "Registry: $REGISTRY_FILE"
echo "Next: restart Hermes and confirm plugin discovery."
