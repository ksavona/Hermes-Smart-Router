#!/bin/bash
set -e

cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router

echo "🔧 Hermes Smart Router - Deploy with pre_llm_call Hook"
echo "=" | awk '{for(i=0;i<80;i++)printf "="}' && echo ""
echo ""

echo "1️⃣  Rebuilding package..."
.venv/bin/pip install -e . --quiet 2>&1 | grep -E "(Successfully|Requirement|ERROR)" | head -3

echo ""
echo "2️⃣  Restarting Hermes gateway..."
hermes gateway restart 2>&1 | tail -3

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🎯 What changed:"
echo "   • Registered pre_llm_call hook (mandatory routing for EVERY message)"
echo "   • Route tool is called automatically BEFORE the model sees each prompt"
echo "   • Routing decisions are persisted to SQLite"
echo "   • Model receives routing context in message flow"
echo ""
echo "🧪 Testing the fix:"
echo "   Terminal 1 (Monitor):"
echo "      .venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20"
echo ""
echo "   Terminal 2 (Hermes):"
echo "      hermes chat"
echo ""
echo "📊 Expected result:"
echo "   • Monitor shows NEW routing runs appearing in real-time"
echo "   • Every prompt you send appears with routing decision"
echo "   • Selected model, fallback, confidence, and reason are shown"
echo ""
