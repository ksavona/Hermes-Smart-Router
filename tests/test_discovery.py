from __future__ import annotations

import sys

from hermes_plugin_starter import cli
from hermes_plugin_starter.config import default_router_config


def test_get_hermes_provider_models_merges_runtime_and_fallback(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "hermes_cli", None)
    monkeypatch.setitem(sys.modules, "hermes_cli.model_switch", None)
    monkeypatch.setitem(sys.modules, "hermes_cli.models", None)
    monkeypatch.setattr(cli, "_get_hermes_provider_models_via_runtime", lambda: {"GitHub Copilot": ["gpt-4o-mini"]})
    monkeypatch.setattr(
        cli,
        "_get_hermes_provider_catalog_fallback",
        lambda: {"GitHub Copilot": ["gpt-5.4"], "OpenAI Codex": ["gpt-5.4-mini"]},
    )

    result = cli._get_hermes_provider_models()

    assert result["GitHub Copilot"] == ["gpt-4o-mini", "gpt-5.4"]
    assert result["OpenAI Codex"] == ["gpt-5.4-mini"]


def test_pricing_backfill_enriches_visible_models(monkeypatch) -> None:
    cfg = default_router_config()
    catalog = {
        "metadata": {},
        "models": [
            {
                "provider": "copilot",
                "model": "gpt-5-mini",
                "estimated_cost_per_1k": 0.00001,
            }
        ],
    }

    monkeypatch.setattr(
        cli,
        "_get_hermes_provider_models",
        lambda: {"GitHub Copilot": ["gpt-4o-mini", "gpt-5-mini"]},
    )

    enriched, added, inferred = cli._enrich_pricing_catalog_with_visible_models(cfg, catalog)

    assert added >= 1
    assert inferred >= 1
    rows = {
        (str(row.get("provider", "")).lower(), str(row.get("model", "")).lower()): row
        for row in enriched.get("models", [])
    }
    assert ("copilot", "gpt-4o-mini") in rows
    assert rows[("copilot", "gpt-4o-mini")].get("estimated_cost_per_1k") is not None
    assert rows[("copilot", "gpt-4o-mini")].get("strength")


def test_tier_table_build_groups_counterparts(monkeypatch) -> None:
    cfg = default_router_config()
    catalog = {
        "metadata": {},
        "models": [
            {"provider": "copilot", "model": "gpt-5-mini", "estimated_cost_per_1k": 0.00001, "capability_class": "cheap"},
            {"provider": "codex", "model": "gpt-5-mini", "estimated_cost_per_1k": 0.00004, "capability_class": "cheap"},
            {"provider": "codex", "model": "gpt-5.5", "estimated_cost_per_1k": 0.001, "capability_class": "premium"},
        ],
    }

    monkeypatch.setattr(
        cli,
        "_get_hermes_provider_models",
        lambda: {"GitHub Copilot": ["gpt-5-mini"], "OpenAI Codex": ["gpt-5-mini", "gpt-5.5"]},
    )

    table = cli._build_tier_model_catalog(cfg, catalog)

    assert "tiers" in table
    assert "T1" in table["tiers"]
    t1_rows = table["tiers"]["T1"]
    assert t1_rows
    grouped_models = [row["primary"]["model"] for row in t1_rows]
    assert "gpt-5-mini" in grouped_models