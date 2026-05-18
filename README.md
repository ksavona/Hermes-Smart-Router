# Hermes Smart Router

![CI](https://github.com/ksavona/Hermes-Smart-Router/actions/workflows/ci.yml/badge.svg)
![Release](https://github.com/ksavona/Hermes-Smart-Router/actions/workflows/release.yml/badge.svg)

Hermes Smart Router is a terminal-first Hermes plugin that routes prompts to the best available model while prioritizing low cost, subscription preservation, and provider reliability.

This repo is structured for community collaboration with clear docs, CI, tests, and one-command installation.

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
python3 -m pip install -e .[dev]
pytest
ruff check .
```

## Pricing Accuracy Workflow

Use a dedicated pricing catalog and sync command so router decisions use current costs.

1. Initialize catalog from current config:

```bash
python3 -m hermes_plugin_starter.cli pricing-init
```

2. Update catalog entries (provider/model cost, source URL, verified timestamp):

```bash
$HOME/.hermes/plugins/hermes-smart-router/pricing_catalog.yaml
```

3. Apply catalog prices to router config:

```bash
python3 -m hermes_plugin_starter.cli pricing-sync
```

4. Check coverage/staleness:

```bash
python3 -m hermes_plugin_starter.cli pricing-report --stale-days 7
```

5. Optional weekly automation:

```bash
bash scripts/weekly_pricing_refresh.sh
```

You can wire a web-enabled updater (LLM/tooling script) by setting:

```bash
export PRICING_LLM_COMMAND='my-web-llm-cli --json'
bash scripts/weekly_pricing_refresh.sh
```

Default behavior without PRICING_LLM_COMMAND:

- The weekly script fetches official OpenAI and Anthropic pricing pages via a text mirror.
- It generates updates JSON and applies those updates to your pricing catalog.
- Then it runs pricing-sync and pricing-report.

By default, `scripts/weekly_pricing_refresh.sh` forces a refresh each run.
Set this to only refresh when due:

```bash
export PRICING_REFRESH_FORCE=0
```

Run only the official fetcher step:

```bash
python3 scripts/fetch_official_pricing.py \
	--catalog "$HOME/.hermes/plugins/hermes-smart-router/pricing_catalog.yaml" \
	--out-json "$HOME/.hermes/plugins/hermes-smart-router/pricing_updates_official.json" \
	--allow-proxy \
	--use-openrouter
```

`--use-openrouter` is a low-confidence fallback source for unmatched model names.
It helps reduce `N/A` entries but should be treated as reference pricing, not official billing.

Standalone updater script usage:

```bash
python3 scripts/update_pricing_catalog.py \
	--catalog "$HOME/.hermes/plugins/hermes-smart-router/pricing_catalog.yaml" \
	--llm-command "$PRICING_LLM_COMMAND"
```

Alternative (no live LLM call): provide a JSON file containing updates:

```bash
python3 scripts/update_pricing_catalog.py \
	--catalog "$HOME/.hermes/plugins/hermes-smart-router/pricing_catalog.yaml" \
	--input-json /path/to/pricing_updates.json
```

## Monitor Pricing Gaps Panel

In monitor follow mode, open the menu and choose **View Pricing Gaps & Suggestions**.
This panel lists visible models with missing prices and suggests closest mapped equivalents
that can be used to populate the pricing catalog.

Then run the weekly script (manually, cron, or systemd timer).

## Current Scope (Phase 1)

- Routing config schema and defaults
- Tier routing engine
- Smart auto routing baseline with score-based candidate selection
- Provider health states and error interpretation
- Local runtime state store for provider health, history, and cost snapshot tracking
- CLI setup, diagnostics, and status commands
- Installer and uninstaller scripts

## Functional Spec

Primary requirements source:

- `docs/hermes_smart_router_functional_document.md`

Implementation docs:

- `docs/ARCHITECTURE.md`
- `docs/INSTALLATION.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/RELEASING.md`

## Releases

Tagged releases follow Semantic Versioning.

- `v0.1.0` is the initial public foundation release.
- Release artifacts are built automatically by GitHub Actions when version tags are pushed.

## Repository Layout

- `src/hermes_plugin_starter/` plugin package
- `scripts/` installer and maintenance scripts
- `docs/` specifications and architecture
- `tests/` automated tests
- `.github/workflows/` CI pipeline

## License

This project is source-available under the Hermes Smart Router Free Use No-Resale License 1.0.

You can use, modify, and share the code freely, but you cannot sell the code or sell access to it without prior written permission.

## Licensing FAQ

### Can I use this in my own Hermes setup?

Yes. Personal, internal, research, educational, and community use are allowed.

### Can I modify the code?

Yes. You can modify it and share your modified version as long as it remains free and includes the same license.

### Can I redistribute it to other people?

Yes, if you do not charge for the code or for access to the code.

### Can I sell this plugin or bundle it into a paid product?

No. Selling the code, selling hosted access to it, or charging for access where the primary value is this software is prohibited without prior written permission.

### Is this open source?

No. It is source-available. The code is visible and reusable under the repository license, but resale is restricted.

## Support and Commercial Permission

### Support

For bug reports, feature requests, and general project feedback, use the GitHub Issues page for this repository.

### Commercial permission requests

If you want to sell the code, bundle it into a paid product, or charge for hosted access that depends on this software, you must obtain prior written permission.

Submit that request directly to the repository owner through GitHub and include:

- your name or company name
- intended commercial use
- distribution model
- whether you plan to modify the software
- expected audience or customer base

## Community Notes

- Keep pull requests focused and documented.
- Add tests for behavior changes.
- Prefer deterministic logic for routing guardrails.
- Review `CHANGELOG.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md` before opening major contributions.
