#!/bin/bash
set -e

echo "Building and redeploying Hermes Smart Router..."
echo ""

cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router

echo "1. Reinstalling package..."
.venv/bin/pip install -e . --quiet

echo "2. Restarting Hermes gateway..."
hermes gateway restart

echo ""
echo "✓ Deployment complete"
echo ""
echo "Next steps:"
echo "1. Start monitor: .venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20"
echo "2. In another terminal, run: hermes chat"
echo "3. Send a prompt and check if it appears in the monitor"
