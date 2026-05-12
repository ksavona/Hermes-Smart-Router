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
- `src/hermes_plugin_starter/cli.py`: Setup and diagnostics command-line interface
- `scripts/install.sh`: One-line installation and registration

## Runtime Flow

1. Hermes discovers plugin from plugin directory.
2. Hermes reads metadata in `manifest.yaml`.
3. Hermes imports the declared entrypoint and calls `register(...)`.
4. Plugin ensures router config exists in local Hermes plugin storage.
5. Router evaluates prompt tier and provider availability.
6. Router returns chosen provider and model plus fallback metadata.

## Data Flow

1. Request comes in as prompt + context.
2. Request is transformed into a `RoutingRequest`.
3. Provider health state is consulted.
4. Tier routing selects the lowest-cost competent available model.
5. Decision can be converted to chat notification payloads for Hermes runtime messages.
