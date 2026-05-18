# Implementation Status

Last updated: 2026-05-14

## Current Snapshot

The project now has a Hermes contract-compatible plugin entrypoint and routing tool registration in `src/hermes_smart_router/`, while preserving the existing routing engine in `src/hermes_plugin_starter/`.

## Completed

- Typed domain models for routing, provider health, and runtime events
- Configuration system with defaults and local YAML persistence
- Deterministic tier routing baseline
- Smart auto routing baseline with confidence-threshold fallback to tier routing
- Provider flexibility preservation scoring in smart auto routing
- Normal-vs-fallback provider filtering during candidate selection
- Provider health state machine baseline and regex-based error interpretation
- Local SQLite runtime state store for provider health, routing history, and cost snapshots
- One-time legacy YAML to SQLite state migration on first run
- Routing history retention policy (default 10 days)
- Full prompt persistence is opt-in for debug (`store_full_prompts_for_debug`)
- Notification payload helper builders for runtime chat messages
- CLI commands:
  - `setup`
  - `doctor`
  - `status`
  - `monitor` (with `--follow`, `--full-prompt`, and `--limit`)
- Installer and uninstaller scripts
- Hermes plugin contract wrapper package:
  - `register(ctx)` entrypoint in `src/hermes_smart_router/__init__.py`
  - `ctx.register_tool(...)` for the `route` tool
  - Tool schema and JSON-returning handler in `src/hermes_smart_router/schemas.py` and `src/hermes_smart_router/tools.py`
- Packaging entry point for Hermes plugin discovery in `pyproject.toml` under `[project.entry-points."hermes_agent.plugins"]`
- Installer registry entrypoint aligned to Hermes contract wrapper (`hermes_smart_router:register`)
- Tests and linting in place (`pytest` passing)

## Deferred / Not Implemented Yet

- Live provider adapters and direct provider probing drivers
- Smart-routing LLM JSON planner (current smart auto is heuristic scoring)
- Terminal interactive UI (Textual screens)
- Learning memory persistence and retrieval
- Dynamic price fetching and analytics dashboard
- Hermes event bus integration for in-chat push notifications
- End-to-end integration tests with live Hermes runtime

## Latest Update: Mandatory Routing via pre_llm_call Hook (2026-05-14)

✅ **FIXED: Routing now happens for EVERY prompt**

**The Problem:** 
- Tools are optional in Hermes - model decides when to use them
- Simple prompts like "hi" or "write a haiku" didn't trigger the route tool

**The Solution:**
- Registered `pre_llm_call` hook that runs BEFORE the LLM sees each message
- Hook automatically routes every prompt without waiting for model decision
- Routing decisions are persisted to SQLite with full traceability
- Model receives routing context in the message flow

**Changes Made:**
- Updated `src/hermes_smart_router/__init__.py` to register `_pre_llm_call_route()` hook
- Hook invokes routing automatically and injects routing context
- Preserves optional route tool for direct invocation if needed

**Testing:**
```bash
# Terminal 1: Monitor routing decisions in real-time
.venv/bin/python -m hermes_plugin_starter monitor --follow --full-prompt --limit 20

# Terminal 2: Send prompts to Hermes
hermes chat
```

Monitor will now show ALL prompts appearing with routing decisions.

## Known Gaps Against Functional Requirements

1. Smart routing still uses heuristic scoring, not a dedicated LLM JSON planning model.
2. Terminal monitor currently supports text output only, not a full Textual TUI screen set.
3. Learning-memory persistence and retention are not implemented yet (retention policy currently applies to routing runs only).

## Phase 2 Backlog (Prioritised)

1. Add provider adapter interface and per-provider drivers.
2. Replace heuristic smart planner with structured LLM JSON decision engine.
3. Implement probe scheduler and recovery orchestration (exponential backoff).
4. Add prompt-hash storage option for routing logs.
5. Build Textual UI screens matching the functional specification.
6. Add Hermes chat notification bridge (event bus integration).
7. Add integration and end-to-end tests.
