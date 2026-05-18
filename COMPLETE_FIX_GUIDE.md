# Hermes Smart Router - Complete Fix & Testing Guide

## Problem Identified

The `pre_llm_call` hook may not be invoked by Hermes, or there's an issue with the hook parameter signature.

## Solution Steps

### Step 1: Rebuild Package with Updated Hook

```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
.venv/bin/pip install -e .
```

Expected output: `Successfully installed hermes-smart-router-0.2.0`

### Step 2: Restart Hermes Gateway

```bash
hermes gateway restart
```

Wait for "gateway started" message.

### Step 3: Run Diagnostic Test

```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
python3 diagnostic_full.py
```

This will show:
- ✓ Plugin registration status
- ✓ Hook function execution
- ✓ Database state
- How many routing runs are recorded

### Step 4: Test in Hermes

**Terminal 1:** Start monitor
```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
.venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20
```

**Terminal 2:** Send prompt
```bash
hermes chat
```

Type: `Test prompt 1` (hit enter)

Then: `Test prompt 2` (hit enter)

Back to **Terminal 1:** Monitor should show new routing runs appearing!

### Step 5: Check Hermes Debug Logs

If monitor doesn't show new runs, check if hook is being called:

```bash
journalctl --user-unit hermes-gateway -n 200 --no-pager | grep ROUTE
```

You should see output like:
```
[ROUTER-PLUGIN] Registering Smart Router plugin...
[ROUTE-HOOK] Called!
[ROUTE-HOOK] Routing succeeded!
```

## Troubleshooting

If hook is NOT being called:

1. **Verify plugin is loaded:**
   ```bash
   hermes plugins list | grep router
   ```
   Should show: `hermes-smart-router` enabled

2. **Check for plugin load errors:**
   ```bash
   HERMES_PLUGINS_DEBUG=1 hermes plugins list 2>&1 | tail -20
   ```

3. **Test route function directly:**
   ```bash
   python3 << 'EOF'
   from src.hermes_smart_router.tools import route
   import json
   result = route({"prompt": "direct test", "context": {}})
   print(json.loads(result))
   EOF
   ```

## What Changed in This Fix

1. **Hook parameter signature** updated to use `**kwargs` only for compatibility
2. **Debug logging** added to stderr to track hook execution
3. **Diagnostic script** (`diagnostic_full.py`) to verify everything works

## Key Indicators

✅ Success indicators:
- Monitor shows new routing runs as you send prompts
- Database contains new entries (not just the old "2+2")
- Debug logs show `[ROUTE-HOOK] Called!` messages

❌ Failure indicators:
- Monitor still shows only 1 old routing run
- No new database entries
- No debug messages in logs

If you see ❌ indicators, the hook system may not be invoking properly in your Hermes installation. This could be a Hermes version issue or a plugin initialization issue.

## Alternative Approach

If the hook doesn't work, we may need to:
1. Check Hermes version (`hermes --version`)
2. Review Hermes plugin documentation for your version
3. Consider implementing routing as a different type of plugin (e.g., model provider plugin)

For now, test these steps and let me know what you see in the monitor and logs!
