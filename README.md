# Hermes Smart Router

Hermes Smart Router is a terminal-first Hermes plugin that routes prompts to the best available model while prioritizing low cost, subscription preservation, and provider reliability.

This repo is structured for open-source collaboration with clear docs, CI, tests, and one-command installation.

## One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/ksavona/Hermes-Smart-Router/main/scripts/install.sh | bash
```

This installer will:

1. Clone the repository into your Hermes plugin directory.
2. Install Python dependencies.
3. Register the plugin in the local Hermes plugin registry.
4. Run setup and diagnostics.

## Local Development

```bash
python -m pip install -e .[dev]
pytest
ruff check .
```

## Current Scope (Phase 1)

- Routing config schema and defaults
- Tier routing engine
- Baseline scoring engine for smart candidate evaluation
- Provider health states and error interpretation
- CLI setup and diagnostics commands
- Installer and uninstaller scripts

## Functional Spec

Primary requirements source:

- `docs/hermes_smart_router_functional_document.md`

Implementation docs:

- `docs/ARCHITECTURE.md`
- `docs/INSTALLATION.md`
- `docs/IMPLEMENTATION_STATUS.md`

## Repository Layout

- `src/hermes_plugin_starter/` plugin package
- `scripts/` installer and maintenance scripts
- `docs/` specifications and architecture
- `tests/` automated tests
- `.github/workflows/` CI pipeline

## Community Notes

- Keep pull requests focused and documented.
- Add tests for behavior changes.
- Prefer deterministic logic for routing guardrails.
