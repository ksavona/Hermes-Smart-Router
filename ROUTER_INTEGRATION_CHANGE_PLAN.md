# Hermes Router Integration Change Plan

## Purpose

This document captures the code changes needed to stop Hermes from bypassing Hermes Smart Router. It is intended as an implementation guide for the developer who owns the Hermes plugin runtime integration.

The current repository already contains routing logic, configuration persistence, health state, and tests for routing decisions. The gap is that the plugin registration path only exposes plugin metadata and does not clearly provide Hermes with an active routing hook, middleware, or provider adapter that Hermes can invoke before selecting a model.

## Current Behavior

Hermes discovers the plugin through `manifest.yaml`, which points to the Python entrypoint:

```yaml
entrypoint: hermes_plugin_starter.plugin:register
```

The installer writes the same entrypoint into the local Hermes plugin registry.

In the current implementation, `register(...)` creates the default router config and returns metadata. The routing-capable class, `HermesSmartRouterPlugin`, exists and has a `route(...)` method, but the registration return value does not expose that object or a route callback to Hermes.

Result: Hermes can discover the plugin but may continue using its normal model-selection path because it has not been handed an active router integration point.

## Required Changes

### 1. Confirm the Hermes plugin registration contract

Before changing code, confirm exactly what Hermes expects from `register(...)`.

Examples of possible contracts:

- `register(context)` returns a plugin object with known methods such as `route(...)`.
- `register(context)` returns a metadata object plus a `hooks` map.
- `register(context)` mutates a provided registry/event bus in `context`.
- `register(context)` returns provider definitions that Hermes later calls.

Why this matters: returning a `HermesSmartRouterPlugin` instance is only correct if Hermes actually introspects returned plugin objects. If Hermes expects hooks to be registered through `context`, returning a router instance alone will still be bypassed.

### 2. Expose an active routing integration from `register(...)`

Once the contract is known, update `src/hermes_plugin_starter/plugin.py` so registration exposes the actual route handler.

If Hermes expects an object return, use this shape:

```python
@dataclass(slots=True)
class HermesSmartRouterPlugin:
    config_path: Path
    name: str = "hermes-smart-router"
    version: str = "0.1.0"
    description: str = "Smart model routing plugin for Hermes with tier and auto modes"

    def route(self, prompt: str, context: dict[str, Any] | None = None) -> RoutingDecision:
        ...


def register(context: dict[str, Any] | None = None) -> HermesSmartRouterPlugin:
    context = context or {}
    config_path = resolve_config_path(context)
    create_default_plugin_config(config_path)
    return HermesSmartRouterPlugin(config_path=config_path)
```

If Hermes expects hook registration, keep metadata return if needed but register the hook explicitly:

```python
def register(context: dict[str, Any] | None = None) -> PluginInfo:
    context = context or {}
    config_path = resolve_config_path(context)
    create_default_plugin_config(config_path)
    plugin = HermesSmartRouterPlugin(config_path=config_path)

    hooks = context.get("hooks") or context.get("registry")
    hooks.register("route", plugin.route)

    return PluginInfo(
        name="hermes-smart-router",
        version="0.1.0",
        description="Smart model routing plugin for Hermes with tier and auto modes",
    )
```

Why this matters: the router cannot affect Hermes model selection unless Hermes receives a callable routing surface and invokes it before sending a prompt to a provider.

### 3. Extract config-path resolution into a small helper

Add a helper in `src/hermes_plugin_starter/plugin.py`:

```python
def resolve_config_path(context: dict[str, Any]) -> Path:
    configured_path = context.get("config_path")
    if configured_path:
        return Path(configured_path)
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_config.yaml"
```

Why this matters: tests and Hermes runtime can supply an isolated config path without writing to the user's real home directory. It also keeps `register(...)` focused on integration rather than path construction.

### 4. Pass task risk from Hermes context into `RoutingRequest`

`RoutingRequest` already supports `risk_level`, and `map_request_to_tier(...)` already maps critical requests to `T5`. The plugin route method should parse `context["risk_level"]` and pass it into the request.

Recommended helper:

```python
def risk_level_from_context(context: dict[str, Any]) -> TaskRiskLevel:
    raw = context.get("risk_level", TaskRiskLevel.LOW)
    if isinstance(raw, TaskRiskLevel):
        return raw
    try:
        return TaskRiskLevel(str(raw).lower())
    except ValueError:
        return TaskRiskLevel.LOW
```

Then update request construction:

```python
request = RoutingRequest(
    prompt=prompt,
    requires_tools=bool(context.get("requires_tools", False)),
    requires_code=bool(context.get("requires_code", False)),
    requires_reasoning=bool(context.get("requires_reasoning", False)),
    required_context_size=int(context.get("required_context_size", 0)),
    risk_level=risk_level_from_context(context),
    user_preference=context.get("user_preference"),
)
```

Why this matters: without this mapping, Hermes can classify a prompt as high-risk or critical, but the router will still treat it as low-risk and may choose too small a tier.

### 5. Fix API fallback detection in smart routing

In `src/hermes_plugin_starter/routing.py`, smart routing currently needs to distinguish provider type from provider health. API fallback eligibility should be based on `ProviderType.FALLBACK`, not `ProviderHealthStatus.STANDBY`.

Required update:

```python
allow_api_fallback=provider_states[selected.provider].provider_type == ProviderType.FALLBACK
```

Also update fallback-provider filtering to compare against `ProviderType.FALLBACK` directly instead of accessing enum values through an instance.

Why this matters: provider type answers “what kind of provider is this?”, while provider health answers “can this provider be used right now?”. Mixing the two can cause fallback/API decisions to be incorrect.

### 6. Add tests before runtime rollout

Add or update tests to cover the integration behavior explicitly.

Recommended tests:

1. `register(...)` exposes the route handler in the exact shape Hermes expects.
2. `register(...)` accepts an injected `config_path` so tests do not write to the real home directory.
3. `route(...)` passes `risk_level=critical` through to `RoutingRequest` and produces a `T5` decision.
4. Smart routing sets `allow_api_fallback=True` when a selected model belongs to a `ProviderType.FALLBACK` provider.
5. Existing metadata expectations remain true if Hermes still requires metadata.

Why this matters: the original bypass was not caught because tests only verified registration metadata. Tests must verify that Hermes receives an executable integration surface, not just name/version strings.

## Suggested Implementation Order

1. Read Hermes plugin runtime docs or source and identify the expected registration contract.
2. Update `register(...)` to expose the route integration using the required contract.
3. Add `resolve_config_path(...)` and risk-level parsing helpers.
4. Update routing provider-type comparisons.
5. Add focused unit tests for registration shape and routing context propagation.
6. Add an integration test or smoke test that simulates Hermes loading the manifest, calling `register(...)`, and invoking the router.
7. Run `pytest -q` and `ruff check .`.
8. Install in a local Hermes environment and confirm routing history is written after a prompt.

## Manual Verification Checklist

After implementation, verify the following in a Hermes runtime:

- Hermes discovers `hermes-smart-router` from the registry.
- Hermes calls `hermes_plugin_starter.plugin:register` during startup.
- Hermes receives a routing hook or object and logs no plugin-contract errors.
- Sending a prompt causes `router_config.yaml` to be read or created.
- Sending a prompt appends an entry to `routing_history.yaml`.
- A critical-risk prompt maps to tier `T5`.
- A fallback API provider is only used when normal providers are unavailable or policy allows fallback.

## Risks and Open Questions

- The exact Hermes plugin contract is not present in this repository. The final code shape must match the Hermes runtime, not an inferred API.
- This repository does not yet implement live provider adapters. Even after Hermes calls the router, another integration layer may still be needed to execute the selected provider/model.
- Real event-bus integration for in-chat notifications is listed as deferred work, so runtime visibility may remain limited until that bridge is implemented.
- Confirmation prompts for paid API fallback are represented in config, but the user-interaction flow is not implemented here yet.

## Definition of Done

The integration should be considered complete when Hermes no longer bypasses the router and a prompt produces a persisted routing decision before provider execution. At minimum, the implementation must prove that Hermes invokes the Smart Router route path and consumes the returned provider/model decision.
