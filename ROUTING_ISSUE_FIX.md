# Router Integration - Status & Next Steps

## Current Situation

The Hermes Smart Router plugin is **installed and registered**, but it's only being invoked selectively by the Hermes model, not for every prompt.

### Why This Happens

Hermes treats tools as **optional helpers** that the LLM model calls when appropriate:
- Simple prompts like "hi" or "write a haiku" → Model doesn't call the route tool
- The model decides routing isn't needed for creative tasks

### Evidence

From the Hermes session logs:
```
Messages: 2 (1 user, 0 tool calls)  ← No tools were called for "hi" prompt
```

## Solution Implemented

✅ **Updated tool schema** (schemas.py) to explicitly state:
- Tool is "REQUIRED"  
- Tool must be called "FIRST for every user message"
- Added detailed context hints

This makes the tool description more compelling and explicit about its mandatory nature.

## Testing the Fix

**Step 1: Deploy updated schema**
```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
bash redeploy.sh
```

**Step 2: Start monitor in Terminal A**
```bash
.venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20
```

**Step 3: Use Hermes in Terminal B**
```bash
hermes chat
```

Then send test prompts like:
- "What is 2+2?"
- "Write a haiku about rain"
- "Explain quantum computing"

**Expected Result:**
- Monitor should show ALL prompts appearing in real-time
- Each should show: selected model, fallback, confidence, and reasoning

## If Tool Still Isn't Called

If the updated schema doesn't work, we may need to:

1. **Implement a Hermes middleware hook** - Intercept requests before the model sees them
2. **Make routing non-optional** - Implement it as a pre-request middleware instead of an optional tool
3. **Contact Hermes team** - Ask if there's a way to force tool invocation

For now, try the schema update first as it's the least invasive change.
