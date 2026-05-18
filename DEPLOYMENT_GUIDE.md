# Final Deployment Steps

## Status: Code Updated ✅

The `src/hermes_smart_router/__init__.py` has been successfully updated to include the `pre_llm_call` hook.

## What's New

The plugin now includes:
1. **`_pre_llm_call_route()` hook** - Runs BEFORE every LLM call
2. **Automatic routing** - Every prompt is routed without waiting for model decision
3. **Mandatory persistence** - All routing decisions recorded to SQLite
4. **Context injection** - Routing info provided to the model

## Deployment Steps

### Step 1: Rebuild the Package

```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
.venv/bin/pip install -e .
```

Expected output: `Successfully installed hermes-smart-router-0.2.0`

### Step 2: Restart Hermes Gateway

```bash
hermes gateway restart
```

Wait for the gateway to restart (should say "gateway started").

### Step 3: Verify Plugin is Loaded

```bash
hermes plugins list | grep -i router
```

Should show: `hermes-smart-router` as enabled

## Testing the Fix

### Terminal 1: Start the Monitor

```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
.venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20
```

This will show routing decisions in real-time.

### Terminal 2: Use Hermes Chat

```bash
hermes chat
```

Send test prompts:
- `What is 2+2?`
- `Write a haiku about rain`
- `Explain quantum mechanics in simple terms`
- `hi`

### Expected Result

The monitor should show:
```
Hermes Smart Router monitor
Showing latest 3 routing runs
Runs: 3 | Smart: 3 | Tier: 0 | Estimated spend: 0.0
────────────────────────────────────────────────────────────────────────────────
Time: 2026-05-14T14:XX:XX.XXXXXX+00:00
Prompt: What is 2+2?
Selected: codex gpt-5-mini
Fallback: ollama qwen-local
Mode/Tier/Confidence: smart_auto / T1 / 90
...
────────────────────────────────────────────────────────────────────────────────
Time: 2026-05-14T14:XX:XX.XXXXXX+00:00
Prompt: Write a haiku about rain
Selected: codex gpt-5-mini
...
```

**Each prompt appears with its routing decision in real-time!**

## Troubleshooting

If routing doesn't appear:

1. **Check plugin is loaded:**
   ```bash
   hermes plugins list
   ```

2. **Check for errors in plugin:**
   ```bash
   HERMES_PLUGINS_DEBUG=1 hermes plugins list 2>&1 | grep router
   ```

3. **Check Hermes gateway logs:**
   ```bash
   journalctl --user-unit hermes-gateway -n 50 --no-pager
   ```

4. **Test route() function directly:**
   ```bash
   .venv/bin/python -c "
   from hermes_smart_router.tools import route
   import json
   result = route({'prompt': 'test', 'context': {}})
   print(json.dumps(json.loads(result), indent=2))
   "
   ```

## Key Changes

The `register()` function in `src/hermes_smart_router/__init__.py` now:
1. Registers the optional `route` tool (for direct invocation)
2. **Registers `_pre_llm_call_route` hook** (for mandatory routing)
3. Provides plugin metadata

This ensures routing happens for EVERY prompt, not just when the model decides to use the tool.
