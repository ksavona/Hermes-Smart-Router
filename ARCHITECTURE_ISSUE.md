# Hermes Smart Router - Architectural Issue & Solution

## Problem Statement

The route tool is **installed and registered correctly**, but it's **not being invoked for new prompts** in Hermes because:

1. **Tools are optional in Hermes** - The LLM model decides when to use them
2. **The model doesn't think routing is needed** - For simple prompts like "hi" or "write a haiku", the model decides routing isn't necessary
3. **Current approach is wrong** - Treating routing as an optional tool violates the functional requirement that routing should happen for EVERY prompt

## Evidence

From Hermes CLI sessions:
```
Messages: 2 (1 user, 0 tool calls)  ← Model chose not to use any tools
```

Monitor shows only 1 routing run (from our diagnostic test), no new runs despite multiple prompts sent.

## Root Cause

The architecture is fundamentally misaligned with Hermes' tool invocation model:
- ❌ Current: Register as optional tool → LLM decides when to call → Unpredictable invocation
- ✅ Required: Mandatory routing for EVERY prompt → Pre-processing/middleware approach

## Solution Approach

We need to implement routing as a **mandatory pre-processing layer**, not as an optional tool. There are three implementation paths:

### Option A: Hermes Middleware/Hook (Recommended)
Check if Hermes supports request interception hooks or middleware:
```python
# Pseudo-code:
@app.before_chat_message
def route_request(message):
    decision = route(message)
    return decision, message
```

### Option B: Custom Hermes Handler
Wrap Hermes' chat handler to route before passing to model:
```python
def hermes_route_and_chat(prompt, context):
    routing_decision = route(prompt, context)
    # Pass both routing decision and prompt to model context
    response = hermes_chat(prompt, context={**context, "routing": routing_decision})
    return response
```

### Option C: Agent Initialization Hook
Register routing at the agent level during initialization, ensuring it runs for every session.

## Next Steps

1. **Investigate Hermes Plugin Architecture**
   - Look for middleware/hook registration in Hermes docs
   - Check if there's a `before_request` or `on_message` hook available
   - Examine other Hermes plugins to see if they use this pattern

2. **Check Hermes Source/Docs**
   - Find plugin lifecycle hooks
   - Look for request interception points
   - Check if there's a way to register pre-request processors

3. **Implement Mandatory Routing**
   - Once we find the hook point, implement routing there
   - Ensure routing happens BEFORE model sees the prompt
   - Pass routing decision to model context

4. **Alternative: Document As-Is**
   - If Hermes doesn't support mandatory hooks, document that routing is optional
   - Users would need to explicitly invoke the route tool
   - This is a limitation of Hermes' tool invocation model, not our implementation

## Current Status

✅ **Completed:**
- Route tool implementation
- SQLite persistence with retention policies
- Plugin registration and schema
- Privacy controls (opt-in full-prompt logging)
- Monitor/debugging commands

❌ **Blocked:**
- Mandatory routing invocation for every prompt
- Need to find/implement Hermes hook system

## Files to Review

- `/hermes_smart_router/__init__.py` - Current tool registration
- `/hermes_smart_router/schemas.py` - Tool schema (updated but ineffective)
- Look for: Hermes plugin docs, hook/middleware patterns
