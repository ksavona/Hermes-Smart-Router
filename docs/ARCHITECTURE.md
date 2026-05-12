# Architecture

## Overview

Hermes Smart Router is implemented as a backend plugin package with deterministic routing, health tracking, and setup tooling.

- `manifest.yaml`: Plugin metadata and declared entrypoint
- `src/hermes_plugin_starter/plugin.py`: Runtime registration and default config bootstrap
- `src/hermes_plugin_starter/models.py`: Core typed domain models
- `src/hermes_plugin_starter/config.py`: Router config schema and YAML persistence
- `src/hermes_plugin_starter/health.py`: Provider error interpretation and status transitions
- `src/hermes_plugin_starter/routing.py`: Tier routing and scoring logic
- `src/hermes_plugin_starter/notifications.py`: Runtime notification payloads
- `src/hermes_plugin_starter/state.py`: Local runtime persistence for provider health, routing history, and cost snapshots
- `src/hermes_plugin_starter/cli.py`: Setup and diagnostics command-line interface
- `scripts/install.sh`: One-line installation and registration

## Runtime Flow

1. Hermes discovers plugin from plugin directory.
2. Hermes reads metadata in `manifest.yaml`.
3. Hermes imports the declared entrypoint and calls `register(...)`.
4. Plugin ensures router config exists in local Hermes plugin storage.
5. Router loads persisted provider health and routing state.
6. Router evaluates smart auto routing or tier routing depending on configuration.
7. Router persists health and routing history snapshots after each decision.
8. Router returns chosen provider and model plus fallback metadata.

## Data Flow

1. Request comes in as prompt + context.
2. Request is transformed into a `RoutingRequest`.
3. Persisted provider health state is loaded.
4. Smart auto routing selects the cheapest competent candidate when confidence is sufficient.
5. Tier routing is used directly or as fallback when smart routing confidence is too low.
6. Routing history and cost snapshot data are updated locally.
7. Decision can be converted to chat notification payloads for Hermes runtime messages.
