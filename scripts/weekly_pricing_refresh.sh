#!/usr/bin/env bash
set -euo pipefail

# Weekly pricing refresh workflow:
# 1) Optionally run external web/LLM updater to rewrite pricing catalog.
# 2) Sync router_config.yaml tier prices from catalog.
# 3) Print coverage report.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CATALOG_PATH="${CATALOG_PATH:-$HOME/.hermes/plugins/hermes-smart-router/pricing_catalog.yaml}"
CONFIG_PATH="${CONFIG_PATH:-$HOME/.hermes/plugins/hermes-smart-router/router_config.yaml}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
	PY_BIN="$ROOT_DIR/.venv/bin/python"
else
	PY_BIN="python3"
fi

# Optional: provide a web-enabled updater command through PRICING_REFRESH_COMMAND.
# Example (replace with your own script):
# Example (replace with your own web-enabled LLM command):
# export PRICING_LLM_COMMAND='my-web-llm-cli --json'
# The updater passes a prompt via stdin and expects JSON on stdout.
PRICING_LLM_COMMAND="${PRICING_LLM_COMMAND:-}"
PRICING_REFRESH_FORCE="${PRICING_REFRESH_FORCE:-1}"
DEFAULT_REFRESH_COMMAND=""
if [[ -n "$PRICING_LLM_COMMAND" ]]; then
	DEFAULT_REFRESH_COMMAND="$PY_BIN scripts/update_pricing_catalog.py --catalog \"$CATALOG_PATH\" --llm-command \"$PRICING_LLM_COMMAND\""
else
	UPDATES_JSON="${PRICING_UPDATES_JSON:-$HOME/.hermes/plugins/hermes-smart-router/pricing_updates_official.json}"
	DEFAULT_REFRESH_COMMAND="$PY_BIN scripts/fetch_official_pricing.py --catalog \"$CATALOG_PATH\" --out-json \"$UPDATES_JSON\" --allow-proxy --use-openrouter && $PY_BIN scripts/update_pricing_catalog.py --catalog \"$CATALOG_PATH\" --input-json \"$UPDATES_JSON\" --strict"
fi
PRICING_REFRESH_COMMAND="${PRICING_REFRESH_COMMAND:-$DEFAULT_REFRESH_COMMAND}"

cd "$ROOT_DIR"

"$PY_BIN" -m hermes_plugin_starter.cli --config "$CONFIG_PATH" pricing-init --catalog "$CATALOG_PATH" || true
if [[ "$PRICING_REFRESH_FORCE" == "1" ]]; then
	"$PY_BIN" -m hermes_plugin_starter.cli --config "$CONFIG_PATH" pricing-refresh --force --catalog "$CATALOG_PATH" --refresh-command "$PRICING_REFRESH_COMMAND"
else
	"$PY_BIN" -m hermes_plugin_starter.cli --config "$CONFIG_PATH" pricing-refresh --catalog "$CATALOG_PATH" --refresh-command "$PRICING_REFRESH_COMMAND"
fi
"$PY_BIN" -m hermes_plugin_starter.cli --config "$CONFIG_PATH" pricing-sync --catalog "$CATALOG_PATH"
"$PY_BIN" -m hermes_plugin_starter.cli --config "$CONFIG_PATH" pricing-report --catalog "$CATALOG_PATH" --stale-days 7

echo "Pricing refresh workflow complete."
