from __future__ import annotations

import argparse
import difflib
import json
import re
import textwrap
from pathlib import Path
import time
import os
import sqlite3
import sys
import tty
import termios
from datetime import datetime, timezone
import subprocess

import yaml

from .config import load_router_config
from .models import ProviderHealthStatus, ProviderModel, ProviderType, RoutingRequest
from .routing import (
    _capability_score,
    _cost_penalty,
    _filter_candidates_by_available_models,
    _filter_candidates_for_provider_rules,
    _overkill_penalty,
    _task_fit_score,
    _underfit_penalty,
    collect_candidate_models,
    provider_flexibility_scores,
)
from .state import RouterStateStore


def default_config_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_config.yaml"


def default_pricing_catalog_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "pricing_catalog.yaml"


def default_tier_catalog_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "tier_model_catalog.yaml"


def _canonical_provider_name(name_or_slug: str) -> str:
    normalized = str(name_or_slug or "").strip().lower()
    aliases = {
        "copilot": "GitHub Copilot",
        "github copilot": "GitHub Copilot",
        "openai codex": "OpenAI Codex",
        "openai-codex": "OpenAI Codex",
        "codex": "OpenAI Codex",
    }
    return aliases.get(normalized, str(name_or_slug or "").strip())


def _runtime_provider_keys(name_or_slug: str) -> list[str]:
    normalized = str(name_or_slug or "").strip().lower()
    aliases = {
        "github copilot": ["github copilot", "copilot"],
        "copilot": ["copilot", "github copilot"],
        "openai codex": ["openai codex", "openai-codex", "codex"],
        "openai-codex": ["openai-codex", "openai codex", "codex"],
        "codex": ["codex", "openai-codex", "openai codex"],
    }
    return aliases.get(normalized, [normalized])


def _merge_provider_models(
    providers_dict: dict[str, list[str]],
    provider_name_or_slug: str,
    models: set[str] | list[str],
) -> None:
    canonical = _canonical_provider_name(provider_name_or_slug)
    existing = set(providers_dict.get(canonical, []))
    existing.update(str(m).strip() for m in models if str(m).strip())
    providers_dict[canonical] = sorted(existing)


def _get_hermes_provider_models_via_runtime() -> dict[str, list[str]]:
    """Query Hermes runtime via its own venv Python to avoid local env import issues."""
    runtime_python = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
    if not runtime_python.exists():
        return {}

    script = r'''
import json
try:
    from hermes_cli.model_switch import list_authenticated_providers
except Exception:
    print("{}")
    raise SystemExit(0)

try:
    from hermes_cli.models import provider_model_ids
except Exception:
    provider_model_ids = None

result = {}
try:
    providers = list_authenticated_providers(current_provider="", current_model="", max_models=512)
except Exception:
    providers = []

for row in providers:
    slug = str(row.get("slug", "") or "").strip().lower()
    name = str(row.get("name", "") or "").strip()
    if not slug:
        continue
    models = {str(m).strip() for m in (row.get("models") or []) if str(m).strip()}
    if provider_model_ids is not None:
        try:
            live = provider_model_ids(slug)
            models.update(str(m).strip() for m in live if str(m).strip())
        except Exception:
            pass
    if not models:
        continue
    result[slug] = {
        "name": name,
        "models": sorted(models),
    }

print(json.dumps(result))
'''
    try:
        proc = subprocess.run(
            [str(runtime_python), "-c", script],
            text=True,
            capture_output=True,
            timeout=25,
            check=False,
        )
    except Exception:
        return {}

    if proc.returncode != 0:
        return {}

    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    providers_dict: dict[str, list[str]] = {}
    for slug, info in data.items():
        if not isinstance(info, dict):
            continue
        name = str(info.get("name", "") or "").strip()
        models = info.get("models") or []
        if not isinstance(models, list):
            continue
        display = name if name else slug
        _merge_provider_models(providers_dict, display, models)
    return providers_dict


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iter_tier_models(tier) -> list[ProviderModel]:
    models = [tier.primary, tier.fallback, tier.secondary_fallback]
    models.extend(getattr(tier, "additional_candidates", []) or [])
    return [model for model in models if model]


def _catalog_from_config(cfg) -> dict:
    models: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for tier in cfg.tiers:
        for model in _iter_tier_models(tier):
            if not model:
                continue
            key = (str(model.provider).strip().lower(), str(model.model).strip().lower())
            if key in seen:
                continue
            seen.add(key)
            models.append(
                {
                    "provider": model.provider,
                    "model": model.model,
                    "estimated_cost_per_1k": float(model.estimated_cost_per_1k),
                    "source_url": "",
                    "verified_at": "",
                    "confidence": "medium",
                }
            )

    # Also include discoverable Hermes models so the catalog can be maintained
    # as a complete weekly source-of-truth, not only current tier references.
    provider_name_to_id = {
        "github copilot": "copilot",
        "openai codex": "codex",
        "openai-codex": "codex",
        "copilot": "copilot",
        "codex": "codex",
    }
    live_models = _get_hermes_provider_models()
    for provider_name, provider_models in live_models.items():
        provider_key = provider_name_to_id.get(str(provider_name).strip().lower(), str(provider_name).strip().lower())
        for model_name in provider_models:
            key = (provider_key, str(model_name).strip().lower())
            if key in seen:
                continue
            seen.add(key)
            models.append(
                {
                    "provider": provider_key,
                    "model": str(model_name).strip(),
                    "estimated_cost_per_1k": None,
                    "source_url": "",
                    "verified_at": "",
                    "confidence": "low",
                }
            )

    return {
        "metadata": {
            "updated_at": _now_utc_iso(),
            "refresh_interval_days": 7,
            "notes": "Maintain with official provider pricing pages. Run pricing-sync after updates.",
        },
        "models": sorted(models, key=lambda item: (item["provider"], item["model"])),
    }


def _load_pricing_catalog(catalog_path: Path) -> dict:
    if not catalog_path.exists():
        return {"metadata": {}, "models": []}
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"metadata": {}, "models": []}
    metadata = data.get("metadata", {})
    models = data.get("models", [])
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(models, list):
        models = []
    return {"metadata": metadata, "models": models}


def _write_pricing_catalog(catalog_path: Path, catalog: dict) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")


def _pricing_key(provider: str, model: str) -> tuple[str, str]:
    return (_provider_slug(provider), str(model).strip().lower())


def _pricing_row_quality(row: dict) -> tuple[int, int, int]:
    has_cost = 1 if row.get("estimated_cost_per_1k") is not None else 0
    confidence = str(row.get("confidence", "") or "").strip().lower()
    confidence_rank = 0
    if confidence in {"high", "verified"}:
        confidence_rank = 3
    elif confidence in {"medium"}:
        confidence_rank = 2
    elif confidence in {"inferred"}:
        confidence_rank = 1
    has_source = 1 if str(row.get("source_url", "") or "").strip() else 0
    return (has_cost, confidence_rank, has_source)


def _pricing_index(catalog: dict) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in catalog.get("models", []):
        provider = row.get("provider")
        model = row.get("model")
        if not provider or not model:
            continue
        key = _pricing_key(provider, model)
        existing = index.get(key)
        if existing is None or _pricing_row_quality(row) >= _pricing_row_quality(existing):
            index[key] = row
    return index


def _provider_slug(provider_name_or_id: str) -> str:
    normalized = str(provider_name_or_id or "").strip().lower()
    aliases = {
        "github copilot": "copilot",
        "copilot": "copilot",
        "openai codex": "codex",
        "openai-codex": "codex",
        "codex": "codex",
    }
    return aliases.get(normalized, normalized)


def _infer_model_family(model_name: str) -> str:
    lower = str(model_name or "").strip().lower()
    for family in ("gpt", "claude", "gemini", "deepseek", "llama", "mistral"):
        if family in lower:
            return family
    return lower.split("-")[0] if "-" in lower else (lower or "unknown")


def _infer_capability_class_from_model_name(model_name: str) -> str:
    lower = str(model_name or "").strip().lower()
    explicit = {
        "gemini-2.5-pro": "strong",
        "gemini-3-pro-preview": "strong",
        "gemini-3.1-pro-preview": "premium",
        "gemini-3-flash-preview": "general",
    }
    if lower in explicit:
        return explicit[lower]
    if any(token in lower for token in ["mini", "nano", "small", "haiku", "flash"]):
        return "cheap"
    if any(token in lower for token in ["pro", "opus", "ultra", "5.5", "4.1", "o1", "sonnet-4.6"]):
        return "premium"
    if any(token in lower for token in ["sonnet", "5.4", "reason", "r1"]):
        return "strong"
    if any(token in lower for token in ["4o", "gpt-4", "gpt-5", "turbo"]):
        return "balanced"
    return "general"


def _strength_text(capability_class: str) -> str:
    table = {
        "cheap": "Everyday small tasks and orchestration",
        "fast": "Fast lightweight responses",
        "general": "General writing and lightweight analysis",
        "balanced": "General coding and planning",
        "strong": "Complex coding and multi-step reasoning",
        "premium": "Critical high-risk reasoning and verification",
    }
    cap = str(capability_class or "").strip().lower()
    return table.get(cap, "General purpose")


def _tier_rank_from_capability(capability_class: str) -> int:
    cap = str(capability_class or "").strip().lower()
    table = {
        "cheap": 1,
        "fast": 1,
        "general": 2,
        "balanced": 3,
        "strong": 4,
        "premium": 5,
    }
    return table.get(cap, 2)


def _infer_tier_rank(model_name: str, capability_class: str | None = None, estimated_cost_per_1k: float | None = None) -> int:
    cap = str(capability_class or "").strip().lower()
    if not cap:
        cap = _infer_capability_class_from_model_name(model_name)
    rank = _tier_rank_from_capability(cap)
    lower = str(model_name or "").strip().lower()

    # Keep low-cost balanced/general models in T2 (fast-general lane).
    if cap in {"balanced", "general"} and estimated_cost_per_1k is not None and estimated_cost_per_1k <= 0.00015:
        rank = min(rank, 2)

    if "mini" in lower and rank > 2:
        return max(1, rank - 1)
    return rank


def _model_counterpart_key(model_name: str) -> str:
    lower = str(model_name or "").strip().lower()
    tokens = [token for token in re.split(r"[^a-z0-9]+", lower) if token]
    if not tokens:
        return lower
    keep = [tok for tok in tokens if tok not in {"preview", "experimental", "exp", "latest"}]
    return "-".join(keep) if keep else lower


def _tier_model_lookup(cfg) -> dict[tuple[str, str], tuple[str, str]]:
    lookup: dict[tuple[str, str], tuple[str, str]] = {}
    for tier in cfg.tiers:
        for model in _iter_tier_models(tier):
            if not model:
                continue
            provider = _provider_slug(model.provider)
            model_name = str(model.model).strip().lower()
            lookup[(provider, model_name)] = (tier.tier, str(model.capability_class or "").strip().lower())
    return lookup


def _provider_flex_rank(cfg) -> dict[str, int]:
    rank: dict[str, int] = {}
    for provider in cfg.providers:
        # Lower rank is less flexible/more preferred as primary counterpart.
        rank[_provider_slug(provider.id)] = 0 if not provider.preserve_for_unique_models else 1
    return rank


def _enrich_pricing_catalog_with_visible_models(cfg, catalog: dict) -> tuple[dict, int, int]:
    models = catalog.get("models", [])
    if not isinstance(models, list):
        models = []
    catalog["models"] = models

    index = _pricing_index(catalog)
    cost_lookup = _build_model_cost_lookup(cfg)
    visible = _get_hermes_provider_models()

    added = 0
    inferred = 0
    official_price_overrides: dict[tuple[str, str], tuple[float, str, str, str]] = {
        # Source: https://ai.google.dev/gemini-api/docs/pricing (input token pricing, converted to /1k)
        ("copilot", "gemini-2.5-pro"): (0.00125, "https://ai.google.dev/gemini-api/docs/pricing", "strong", "Complex coding and multi-step reasoning"),
        ("copilot", "gemini-3-flash-preview"): (0.00050, "https://ai.google.dev/gemini-api/docs/pricing", "general", "General writing and lightweight analysis"),
        ("copilot", "gemini-3-pro-preview"): (0.00200, "https://ai.google.dev/gemini-api/docs/pricing", "strong", "Complex coding and multi-step reasoning"),
        ("copilot", "gemini-3.1-pro-preview"): (0.00200, "https://ai.google.dev/gemini-api/docs/pricing", "premium", "Critical high-risk reasoning and verification"),
    }

    for provider_name, provider_models in sorted(visible.items()):
        provider_slug = _provider_slug(provider_name)
        for model_name in sorted(provider_models):
            model_key = str(model_name or "").strip().lower()
            if not model_key:
                continue
            key = (provider_slug, model_key)
            row = index.get(key)
            if row is None:
                row = {
                    "provider": provider_slug,
                    "model": str(model_name).strip(),
                    "estimated_cost_per_1k": None,
                    "source_url": "",
                    "verified_at": "",
                    "confidence": "low",
                }
                models.append(row)
                index[key] = row
                added += 1

            cap = str(row.get("capability_class", "") or "").strip().lower() or _infer_capability_class_from_model_name(model_name)
            row["capability_class"] = cap
            row["strength"] = str(row.get("strength", "") or "").strip() or _strength_text(cap)

            override = official_price_overrides.get((provider_slug, model_key))
            if override is not None:
                price, source_url, cap_override, strength_override = override
                row["estimated_cost_per_1k"] = float(price)
                row["source_url"] = source_url
                row["verified_at"] = _now_utc_iso()
                row["confidence"] = "high"
                row["capability_class"] = cap_override
                row["strength"] = strength_override
                continue

            has_cost = row.get("estimated_cost_per_1k") is not None
            if has_cost:
                continue

            suggestion = _suggest_pricing_equivalent(provider_name, model_name, cost_lookup)
            if suggestion is None:
                continue

            s_model, s_cost, s_provider = suggestion
            row["estimated_cost_per_1k"] = float(s_cost)
            row["source_url"] = f"inferred-equivalent:{s_provider}/{s_model}"
            row["confidence"] = "inferred"
            if not row.get("verified_at"):
                row["verified_at"] = _now_utc_iso()
            inferred += 1

    catalog.setdefault("metadata", {})
    catalog["metadata"]["updated_at"] = _now_utc_iso()
    catalog["metadata"]["refresh_interval_days"] = 7
    notes = str(catalog["metadata"].get("notes", "") or "").strip()
    if not notes:
        catalog["metadata"]["notes"] = (
            "Maintain from official pricing pages and model databases weekly. "
            "Inferred costs should be replaced with verified values."
        )

    catalog["models"] = sorted(
        models,
        key=lambda item: (
            str(item.get("provider", "") or ""),
            str(item.get("model", "") or ""),
        ),
    )
    return catalog, added, inferred


def _build_tier_model_catalog(cfg, catalog: dict) -> dict:
    index = _pricing_index(catalog)
    tier_lookup = _tier_model_lookup(cfg)
    flex_rank = _provider_flex_rank(cfg)
    visible = _get_hermes_provider_models()

    rows_by_tier: dict[str, list[dict]] = {f"T{i}": [] for i in range(1, 6)}
    grouped: dict[tuple[str, str], list[dict]] = {}

    for provider_name, models in sorted(visible.items()):
        provider_slug = _provider_slug(provider_name)
        for model_name in sorted(models):
            raw_model = str(model_name or "").strip()
            if not raw_model:
                continue
            model_key = raw_model.lower()
            pricing = index.get((provider_slug, model_key), {})
            cost_raw = pricing.get("estimated_cost_per_1k")
            try:
                cost = None if cost_raw is None else float(cost_raw)
            except Exception:
                cost = None

            tier_hint, cap_hint = tier_lookup.get((provider_slug, model_key), ("", ""))
            capability = str(pricing.get("capability_class", "") or "").strip().lower() or cap_hint or _infer_capability_class_from_model_name(raw_model)
            strength = str(pricing.get("strength", "") or "").strip() or _strength_text(capability)

            rank = int(tier_hint[1:]) if tier_hint.startswith("T") and tier_hint[1:].isdigit() else _infer_tier_rank(raw_model, capability, cost)
            rank = min(5, max(1, rank))
            tier = f"T{rank}"

            entry = {
                "provider": provider_slug,
                "provider_display": _canonical_provider_name(provider_slug),
                "model": raw_model,
                "price_per_1k": cost,
                "capability_class": capability,
                "strength": strength,
                "is_priced": cost is not None,
                "provider_flex_rank": int(flex_rank.get(provider_slug, 2)),
            }

            group_key = (tier, _model_counterpart_key(raw_model))
            grouped.setdefault(group_key, []).append(entry)

    for (tier, _), entries in grouped.items():
        ordered = sorted(
            entries,
            key=lambda e: (
                int(e["provider_flex_rank"]),
                float(e["price_per_1k"]) if e["price_per_1k"] is not None else float("inf"),
                str(e["provider"]),
                str(e["model"]),
            ),
        )
        primary = ordered[0]
        counterparts = ordered[1:]
        min_price = min(
            [float(e["price_per_1k"]) for e in ordered if e["price_per_1k"] is not None],
            default=float("inf"),
        )

        rows_by_tier[tier].append(
            {
                "primary": primary,
                "counterparts": counterparts,
                "row_min_price": None if min_price == float("inf") else min_price,
            }
        )

    for tier in rows_by_tier:
        rows_by_tier[tier].sort(
            key=lambda row: (
                float(row["row_min_price"]) if row["row_min_price"] is not None else float("inf"),
                str(row["primary"]["model"]),
            )
        )

    return {
        "metadata": {
            "updated_at": _now_utc_iso(),
            "refresh_interval_days": 7,
            "notes": "Weekly tier model table. Fill inferred prices with verified source values.",
        },
        "tiers": rows_by_tier,
    }


def _write_tier_model_catalog(output_path: Path, table: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(table, sort_keys=False), encoding="utf-8")


def _write_tier_model_markdown(output_path: Path, table: dict) -> Path:
    md_path = output_path.with_suffix(".md")

    def _price_text(value: float | None) -> str:
        return "N/A" if value is None else f"${value:.5f}/1k"

    lines: list[str] = [
        "# Weekly Tier Model Table",
        "",
        f"Updated at: {table.get('metadata', {}).get('updated_at', '')}",
        "",
        "Fields: Primary/Price/Strength and counterpart models from flexible providers.",
        "",
    ]

    tiers = table.get("tiers", {}) or {}
    for tier_name in ["T1", "T2", "T3", "T4", "T5"]:
        lines.append(f"## {tier_name}")
        lines.append("")
        lines.append("| Primary | Price | Strength | Counterparts |")
        lines.append("|---|---:|---|---|")

        for row in tiers.get(tier_name, []) or []:
            primary = row.get("primary", {})
            counterparts = row.get("counterparts", []) or []
            primary_text = f"{primary.get('provider', '-')}/{primary.get('model', '-')}"
            primary_price = _price_text(primary.get("price_per_1k"))
            primary_strength = str(primary.get("strength", "") or "-")

            counterpart_text_parts: list[str] = []
            for cp in counterparts:
                cp_text = (
                    f"{cp.get('provider', '-')}/{cp.get('model', '-')} "
                    f"({ _price_text(cp.get('price_per_1k')) }, {cp.get('strength', '-')})"
                )
                counterpart_text_parts.append(cp_text)
            counterpart_text = " ; ".join(counterpart_text_parts) if counterpart_text_parts else "-"

            lines.append(f"| {primary_text} | {primary_price} | {primary_strength} | {counterpart_text} |")

        if not (tiers.get(tier_name, []) or []):
            lines.append("| - | - | - | - |")
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def cmd_pricing_backfill(config_path: Path, catalog_path: Path, dry_run: bool = False) -> int:
    cfg = load_router_config(config_path)
    catalog = _load_pricing_catalog(catalog_path)
    enriched, added, inferred = _enrich_pricing_catalog_with_visible_models(cfg, catalog)

    unresolved = 0
    for row in enriched.get("models", []) or []:
        if row.get("estimated_cost_per_1k") is None:
            unresolved += 1

    if not dry_run:
        _write_pricing_catalog(catalog_path, enriched)

    print("Pricing backfill complete")
    print(f"Config: {config_path}")
    print(f"Catalog: {catalog_path}")
    print(f"Added visible models: {added}")
    print(f"Inferred missing prices from equivalents: {inferred}")
    print(f"Still unresolved prices: {unresolved}")
    print(f"Dry run: {'yes' if dry_run else 'no'}")
    return 0


def cmd_tier_table_build(
    config_path: Path,
    catalog_path: Path,
    output_path: Path,
    backfill_pricing: bool = True,
    dry_run: bool = False,
) -> int:
    cfg = load_router_config(config_path)
    catalog = _load_pricing_catalog(catalog_path)

    added = 0
    inferred = 0
    if backfill_pricing:
        catalog, added, inferred = _enrich_pricing_catalog_with_visible_models(cfg, catalog)

    table = _build_tier_model_catalog(cfg, catalog)

    if not dry_run:
        if backfill_pricing:
            _write_pricing_catalog(catalog_path, catalog)
        _write_tier_model_catalog(output_path, table)
        md_path = _write_tier_model_markdown(output_path, table)
    else:
        md_path = output_path.with_suffix(".md")

    unresolved = 0
    unresolved_models: list[str] = []
    total_rows = 0
    for tier_rows in (table.get("tiers", {}) or {}).values():
        for row in tier_rows:
            total_rows += 1
            primary = row.get("primary", {})
            if primary.get("price_per_1k") is None:
                unresolved += 1
                unresolved_models.append(f"{primary.get('provider', '?')}/{primary.get('model', '?')}")
            for cp in row.get("counterparts", []) or []:
                if cp.get("price_per_1k") is None:
                    unresolved += 1
                    unresolved_models.append(f"{cp.get('provider', '?')}/{cp.get('model', '?')}")

    print("Tier model table build complete")
    print(f"Config: {config_path}")
    print(f"Catalog: {catalog_path}")
    print(f"Tier catalog yaml: {output_path}")
    print(f"Tier catalog markdown: {md_path}")
    print(f"Backfill enabled: {'yes' if backfill_pricing else 'no'}")
    print(f"Added visible models to pricing catalog: {added}")
    print(f"Inferred missing prices: {inferred}")
    print(f"Tier rows: {total_rows}")
    print(f"Unresolved prices in tier table: {unresolved}")
    if unresolved_models:
        print("Unresolved model prices (verify from provider/API database):")
        for model_ref in sorted(set(unresolved_models))[:40]:
            print(f"- {model_ref}")
    print(f"Dry run: {'yes' if dry_run else 'no'}")
    return 0


def _config_model_refs(cfg) -> list[tuple[str, str, object]]:
    refs: list[tuple[str, str, object]] = []
    for tier in cfg.tiers:
        for model in _iter_tier_models(tier):
            if not model:
                continue
            refs.append((model.provider, model.model, model))
    return refs


def _save_router_config(config_path: Path, cfg) -> None:
    from .config import _to_serializable

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(_to_serializable(cfg), sort_keys=False), encoding="utf-8")


def cmd_expand_tiers(config_path: Path, catalog_path: Path, dry_run: bool = False) -> int:
    """Expand tier configuration to include all discovered Hermes models as candidates.
    
    This ensures all available models can be considered for routing, not just those
    explicitly configured in tiers.
    """
    _clear_screen()
    print("\n┌─ Tier Expansion ───────────────────────────────────────────────┐")
    print("│ Adding discovered models to tier configuration as candidates    │")
    print("└────────────────────────────────────────────────────────────────┘\n")
    
    cfg = load_router_config(config_path)
    catalog = _load_pricing_catalog(catalog_path)
    
    # Get all discovered models
    live_models = _get_hermes_provider_models()
    price_index = _pricing_index(catalog)
    
    # Collect currently configured models
    configured = set()
    for tier in cfg.tiers:
        for m in _iter_tier_models(tier):
            if m:
                configured.add((m.provider, m.model))
    
    # Categorize discovered models by estimated capability
    model_capability = {}
    
    # Model name patterns for capability estimation (simple heuristic)
    mini_patterns = ["mini", "small", "3.5", "4o-mini"]  # Low capability
    standard_patterns = ["4o", "gpt-4", "gpt-5", "sonnet-4.5"]  # Medium/high
    premium_patterns = ["4-turbo", "gpt-5.4", "gpt-5.5", "opus", "sonnet-4.6", "pro"]  # Premium
    
    for provider, models in live_models.items():
        provider_key = provider.lower().replace(" ", "-")
        if "copilot" in provider_key:
            provider_key = "copilot"
        elif "codex" in provider_key:
            provider_key = "codex"
        
        for model in models:
            model_lower = model.lower()
            
            # Estimate capability tier
            if any(p in model_lower for p in mini_patterns):
                tier_rank = 1  # T1
            elif any(p in model_lower for p in premium_patterns):
                tier_rank = 5  # T5
            elif any(p in model_lower for p in standard_patterns):
                tier_rank = 3 if "gpt-5" in model_lower else 2  # T3 or T2
            else:
                tier_rank = 2  # Default to T2
            
            # Get price if available
            price_key = _pricing_key(provider_key, model)
            price_entry = price_index.get(price_key)
            estimated_cost = 0.001 if not price_entry else (price_entry.get("estimated_cost_per_1k") or 0.001)
            
            model_capability[(provider_key, model)] = {
                "tier_rank": tier_rank,
                "cost": estimated_cost,
                "configured": (provider_key, model) in configured,
            }
    
    # Add new models to appropriate tiers as secondary/fallback candidates
    added_count = 0
    for (provider, model), info in sorted(model_capability.items()):
        if info["configured"]:
            continue
        
        tier_rank = info["tier_rank"]
        cost = info["cost"]
        target_tier = cfg.tiers[tier_rank - 1] if tier_rank <= len(cfg.tiers) else cfg.tiers[-1]
        
        pm = ProviderModel(
            provider=provider,
            model=model,
            provider_type=ProviderType.NORMAL,
            priority=3 if tier_rank <= 2 else 2,  # Lower priority for additions
            estimated_cost_per_1k=cost,
            latency_ms_estimate=200,
            capability_class="general",
            model_family=model.split("-")[0] if "-" in model else model,
        )
        
        # Add to tier pool, keeping primary/fallback slots intact.
        if not target_tier.secondary_fallback:
            target_tier.secondary_fallback = pm
            added_count += 1
            print(f"✓ Added {provider}/{model} to T{tier_rank} (secondary fallback) - ${cost:.6f}/1k")
        elif not target_tier.fallback:
            target_tier.fallback = pm
            added_count += 1
            print(f"✓ Added {provider}/{model} to T{tier_rank} (fallback) - ${cost:.6f}/1k")
        else:
            extra = getattr(target_tier, "additional_candidates", [])
            extra.append(pm)
            extra.sort(key=lambda candidate: (float(candidate.estimated_cost_per_1k), int(candidate.priority), candidate.model))
            target_tier.additional_candidates = extra
            added_count += 1
            print(f"✓ Added {provider}/{model} to T{tier_rank} (candidate pool) - ${cost:.6f}/1k")
    
    print(f"\nSummary: Added {added_count} new models to tier configuration")
    
    if not dry_run and added_count > 0:
        _save_router_config(config_path, cfg)
        print(f"✓ Configuration saved to {config_path}")
    elif dry_run:
        print(f"[DRY RUN] Changes not saved. Remove --dry-run to apply.")
    
    input("\nPress Enter to return...")
    return 0


def cmd_debug_provider_payload(verbose: bool = False) -> int:
    """Print raw provider discovery payload from Hermes runtime."""
    _clear_screen()
    print("╭─ Provider Discovery Payload (Raw) ─────────────────╮")
    print("│ Source: Live Hermes Runtime                        │")
    print("╰──────────────────────────────────────────────────────╯\n")
    
    live = _get_hermes_provider_models_via_runtime()
    import json
    if live:
        for provider, models in sorted(live.items()):
            print(f"Provider: {provider}")
            print(f"  Count: {len(models)}")
            if verbose:
                print(f"  Models: {sorted(models)}")
            else:
                print(f"  Models: {sorted(models)[:5]} ... (showing first 5, use --verbose for all)")
            print()
    else:
        print("[No live data - using fallback]")
        fallback = _get_hermes_provider_catalog_fallback()
        for provider, models in sorted(fallback.items()):
            print(f"Provider: {provider}")
            print(f"  Count: {len(models)}")
            if verbose:
                print(f"  Models: {sorted(models)}")
            else:
                print(f"  Models: {sorted(models)[:5]} ... (showing first 5, use --verbose for all)")
            print()
    
    input("Press Enter to return...")
    return 0


def cmd_pricing_init(config_path: Path, catalog_path: Path, force: bool) -> int:
    cfg = load_router_config(config_path)
    if catalog_path.exists() and not force:
        print(f"Pricing catalog already exists: {catalog_path}")
        print("Use --force to recreate it from current router config.")
        return 1

    catalog = _catalog_from_config(cfg)
    _write_pricing_catalog(catalog_path, catalog)
    print("Pricing catalog initialized.")
    print(f"Catalog: {catalog_path}")
    print(f"Model entries: {len(catalog.get('models', []))}")
    return 0


def cmd_pricing_report(config_path: Path, catalog_path: Path, stale_days: int) -> int:
    cfg = load_router_config(config_path)
    catalog = _load_pricing_catalog(catalog_path)
    index = _pricing_index(catalog)
    refs = _config_model_refs(cfg)

    configured_keys = {_pricing_key(provider, model) for provider, model, _ in refs}
    covered = sorted([key for key in configured_keys if key in index])
    missing = sorted([key for key in configured_keys if key not in index])
    invalid_cost: list[tuple[str, str]] = []
    valid_cost = 0
    for key in covered:
        row = index.get(key, {})
        try:
            value = row.get("estimated_cost_per_1k")
            if value is None:
                raise ValueError("missing")
            float(value)
            valid_cost += 1
        except Exception:
            invalid_cost.append(key)

    metadata = catalog.get("metadata", {})
    updated_at = str(metadata.get("updated_at", "")).strip()
    refresh_interval = int(metadata.get("refresh_interval_days", 7) or 7)
    stale = False
    if updated_at:
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age_days = int((datetime.now(timezone.utc) - updated_dt).total_seconds() // 86400)
            stale = age_days >= stale_days
        except Exception:
            age_days = -1
    else:
        age_days = -1

    print("Pricing coverage report")
    print(f"Config: {config_path}")
    print(f"Catalog: {catalog_path}")
    print(f"Configured model refs: {len(configured_keys)}")
    print(f"Catalog entries: {len(index)}")
    print(f"Covered refs: {len(covered)}")
    print(f"Covered refs with valid numeric cost: {valid_cost}")
    print(f"Missing refs: {len(missing)}")
    print(f"Refs with missing/invalid cost: {len(invalid_cost)}")
    if age_days >= 0:
        print(f"Catalog age: {age_days} days (target <= {stale_days} days, interval={refresh_interval})")
    else:
        print("Catalog age: unknown (set metadata.updated_at)")
    print(f"Catalog stale: {'yes' if stale else 'no'}")

    if missing:
        print("\nMissing pricing entries:")
        for provider, model in missing:
            print(f"- {provider}/{model}")

    if invalid_cost:
        print("\nEntries needing cost value:")
        for provider, model in invalid_cost:
            print(f"- {provider}/{model}")

    return 0


def cmd_pricing_sync(config_path: Path, catalog_path: Path, dry_run: bool) -> int:
    cfg = load_router_config(config_path)
    catalog = _load_pricing_catalog(catalog_path)
    index = _pricing_index(catalog)

    updated = 0
    unchanged = 0
    missing = 0

    for tier in cfg.tiers:
        for model in _iter_tier_models(tier):
            if not model:
                continue
            entry = index.get(_pricing_key(model.provider, model.model))
            if not entry:
                missing += 1
                continue

            try:
                new_cost = float(entry.get("estimated_cost_per_1k"))
            except Exception:
                missing += 1
                continue

            old_cost = float(model.estimated_cost_per_1k)
            if abs(old_cost - new_cost) < 1e-12:
                unchanged += 1
                continue

            model.estimated_cost_per_1k = new_cost
            updated += 1

    if not dry_run:
        _save_router_config(config_path, cfg)

    print("Pricing sync complete")
    print(f"Config: {config_path}")
    print(f"Catalog: {catalog_path}")
    print(f"Updated model refs: {updated}")
    print(f"Unchanged model refs: {unchanged}")
    print(f"Missing/invalid refs: {missing}")
    print(f"Dry run: {'yes' if dry_run else 'no'}")
    return 0


def cmd_pricing_refresh(catalog_path: Path, refresh_command: str | None, force: bool = False) -> int:
    catalog = _load_pricing_catalog(catalog_path)
    metadata = catalog.get("metadata", {})
    updated_at = str(metadata.get("updated_at", "")).strip()
    interval_days = int(metadata.get("refresh_interval_days", 7) or 7)

    due = True
    if updated_at:
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age_days = int((datetime.now(timezone.utc) - updated_dt).total_seconds() // 86400)
            due = age_days >= interval_days
            print(f"Catalog age: {age_days} days (interval={interval_days})")
        except Exception:
            print("Catalog age: unknown (invalid metadata.updated_at)")
    else:
        print("Catalog age: unknown (metadata.updated_at missing)")

    if force:
        due = True
        print("Force refresh enabled.")

    if not due:
        print("Pricing catalog is not due for refresh yet.")
        return 0

    print("Pricing catalog is due for refresh.")
    if not refresh_command:
        print("No refresh command configured.")
        print("Suggestion: run your web-enabled LLM script to update pricing_catalog.yaml, then run pricing-sync.")
        return 0

    print(f"Running refresh command: {refresh_command}")
    result = subprocess.run(refresh_command, shell=True)
    if result.returncode != 0:
        print(f"Refresh command failed with exit code {result.returncode}")
        return result.returncode

    refreshed = _load_pricing_catalog(catalog_path)
    refreshed.setdefault("metadata", {})
    refreshed["metadata"]["updated_at"] = _now_utc_iso()
    _write_pricing_catalog(catalog_path, refreshed)
    print("Pricing catalog refreshed and timestamp updated.")
    return 0


def cmd_setup(config_path: Path) -> int:
    cfg = load_router_config(config_path)
    print("Hermes Smart Router setup complete.")
    print(f"Config: {config_path}")
    print(f"Routing mode: {cfg.settings.routing_mode.value}")
    print(f"Providers configured: {len(cfg.providers)}")
    return 0


def cmd_doctor(config_path: Path) -> int:
    cfg = load_router_config(config_path)
    store = RouterStateStore(
        config_path.parent,
        history_retention_days=cfg.settings.routing_history_retention_days,
        persist_full_prompts=cfg.settings.store_full_prompts_for_debug,
    )
    snapshot = store.load_cost_snapshot()
    print("Hermes Smart Router diagnostics")
    print(f"Config loaded: {config_path}")
    print(f"Tier count: {len(cfg.tiers)}")
    enabled = [p.id for p in cfg.providers if p.enabled]
    print(f"Enabled providers: {', '.join(enabled) if enabled else 'none'}")
    if snapshot:
        print(f"Tracked runs: {snapshot.get('run_count', 0)}")
        print(f"Estimated API spend: {snapshot.get('estimated_api_spend', 0.0)}")
    return 0


def cmd_status(config_path: Path) -> int:
    cfg = load_router_config(config_path)
    store = RouterStateStore(
        config_path.parent,
        history_retention_days=cfg.settings.routing_history_retention_days,
        persist_full_prompts=cfg.settings.store_full_prompts_for_debug,
    )
    health = store.load_provider_states([])
    history = store.load_history()
    snapshot = store.load_cost_snapshot()

    print("Hermes Smart Router status")
    print(f"History entries: {len(history)}")
    if snapshot:
        print(f"Smart auto runs: {snapshot.get('smart_auto_runs', 0)}")
        print(f"Tier runs: {snapshot.get('tier_runs', 0)}")
        print(f"Estimated API spend: {snapshot.get('estimated_api_spend', 0.0)}")
    if health:
        print("Provider health:")
        for provider_id, state in sorted(health.items()):
            print(f"- {provider_id}: {state.status.value}")
    return 0


def _get_max_routing_id(db_path: Path) -> int:
    """Get the maximum routing run ID from the database."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT MAX(id) as max_id FROM routing_runs").fetchone()
        conn.close()
        return row[0] or 0
    except Exception:
        return 0


def _get_new_routing_decisions(db_path: Path, after_id: int, limit: int = 100) -> list[dict]:
    """Fetch routing decisions with ID > after_id from the database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM routing_runs WHERE id > ? ORDER BY id ASC LIMIT ?",
            (after_id, limit)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _clear_screen() -> None:
    """Clear terminal screen."""
    os.system('clear' if os.name == 'posix' else 'cls')


def _format_box_line(text: str, width: int = 80, pad_char: str = " ") -> str:
    """Format text within a box with proper truncation and padding."""
    max_content_width = width - 4  # Account for "│ " and " │"
    if len(text) > max_content_width:
        text = text[:max_content_width - 3] + "..."
    return f"│ {text:<{max_content_width}}{pad_char}│"


def _print_box_wrapped(text: str, width: int = 80, indent: str = "") -> None:
    """Print text in a box without truncation by wrapping to available width."""
    max_content_width = width - 4
    wrapper = textwrap.TextWrapper(
        width=max(10, max_content_width - len(indent)),
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )

    lines = str(text).split("\n") if text is not None else [""]
    for raw_line in lines:
        wrapped = wrapper.wrap(raw_line) if raw_line else [""]
        for chunk in wrapped:
            content = f"{indent}{chunk}"
            print(f"│ {content:<{max_content_width}}│")


def _print_routing_decision(item: dict) -> None:
    """Display a single routing decision in formatted box layout."""
    _clear_screen()
    width = 80
    
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "⚙ HERMES SMART ROUTER DECISION".center(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")
    
    # Prompt section
    prompt_text = item.get("prompt_text") or ""
    prompt = prompt_text if prompt_text else item.get("prompt_preview", "")
    if len(prompt) > width - 6:
        prompt = prompt[:width - 9] + "..."
    print(_format_box_line(f"Prompt: {prompt}", width))
    print("├" + "─" * (width - 2) + "┤")
    
    # Decision section
    selected_provider = item.get("selected_provider", "none")
    selected_model = item.get("selected_model", "none")
    selected_line = f"Selected: {selected_provider}/{selected_model}"
    print(_format_box_line(selected_line, width))
    
    if item.get("fallback_provider"):
        fallback_provider = item.get("fallback_provider", "none")
        fallback_model = item.get("fallback_model", "none")
        fallback_line = f"Fallback: {fallback_provider}/{fallback_model}"
        print(_format_box_line(fallback_line, width))
    
    print("├" + "─" * (width - 2) + "┤")
    
    # Routing metadata
    mode = item.get("routing_mode", "unknown")
    tier = item.get("tier_equivalent", "unknown")
    confidence = item.get("confidence", 0)
    cost = item.get("estimated_cost", 0.0)
    reason = item.get("routing_reason", "")
    
    metadata_line = f"Mode/Tier/Confidence: {mode} / {tier} / {confidence}%"
    print(_format_box_line(metadata_line, width))
    
    cost_line = f"Estimated Cost: ${cost}"
    print(_format_box_line(cost_line, width))
    
    print("├" + "─" * (width - 2) + "┤")
    reason_preview = reason[:width - 12] if reason else ""
    print(_format_box_line(f"Reason: {reason_preview}", width))
    
    print("╰" + "─" * (width - 2) + "╯")


def _get_terminal_char() -> str:
    """Read a single character from terminal (non-blocking)."""
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            char = sys.stdin.read(1)
            return char
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return ""


def _show_menu() -> str:
    """Display interactive arrow-key menu and return user choice."""
    width = 50
    menu_items = [
        "View Full Prompt",
        "View Routing Reasoning",
        "View Smart Routing Scores",
        "View Pricing Gaps & Suggestions",
        "View Available Models & Providers",
        "View Router Configuration",
        "Back to Monitor"
    ]
    
    selected = 0
    
    while True:
        _clear_screen()
        print("\n╭" + "─" * (width - 2) + "╮")
        print("│" + " MENU".ljust(width - 2) + "│")
        print("├" + "─" * (width - 2) + "┤")
        
        for idx, item in enumerate(menu_items):
            prefix = "▶ " if idx == selected else "  "
            line = f"{prefix}{item}".ljust(width - 2)
            print(f"│{line}│")
        
        print("╰" + "─" * (width - 2) + "╯")
        print("\n(Use arrow keys to navigate, Enter to select)")
        
        char = _get_terminal_char()
        if char == '\x1b':  # Escape sequence
            char = _get_terminal_char()
            if char == '[':
                direction = _get_terminal_char()
                if direction == 'A':  # Up arrow
                    selected = (selected - 1) % len(menu_items)
                elif direction == 'B':  # Down arrow
                    selected = (selected + 1) % len(menu_items)
        elif char == '\r' or char == '\n':  # Enter
            return str(selected + 1)


def _get_hermes_provider_models() -> dict[str, list[str]]:
    """Fetch available providers and models from Hermes sources.
    
    Returns dict of {provider_name: [model1, model2, ...]}
    Merges live runtime discovery with config/history fallback data so the
    display reflects both authenticated models and locally known candidates.
    """
    providers_dict: dict[str, list[str]] = {}

    try:
        from hermes_cli.model_switch import list_authenticated_providers
    except ImportError:
        runtime_data = _get_hermes_provider_models_via_runtime()
    else:
        try:
            from hermes_cli.models import provider_model_ids  # type: ignore
        except Exception:
            provider_model_ids = None

        try:
            providers = list_authenticated_providers(current_provider="", current_model="", max_models=512)
        except Exception:
            runtime_data = _get_hermes_provider_models_via_runtime()
        else:
            runtime_data = {}
            for row in providers:
                name = str(row.get("name", "") or "").strip()
                slug = str(row.get("slug", "") or "").strip().lower()

                if not slug or not name:
                    continue

                models = set(str(m).strip() for m in (row.get("models") or []) if str(m).strip())

                if provider_model_ids is not None:
                    try:
                        live = provider_model_ids(slug)
                        if live:
                            models.update(str(m).strip() for m in live if str(m).strip())
                    except Exception:
                        pass

                if models:
                    _merge_provider_models(runtime_data, name or slug, sorted(list(models)))

    if runtime_data:
        for provider_name, models in runtime_data.items():
            _merge_provider_models(providers_dict, provider_name, models)

    fallback_data = _get_hermes_provider_catalog_fallback()
    for provider_name, models in fallback_data.items():
        _merge_provider_models(providers_dict, provider_name, models)

    return providers_dict if providers_dict else fallback_data


def _get_hermes_provider_catalog_fallback() -> dict[str, list[str]]:
    """Fallback: Build provider/model catalog from local runtime state only.

    Used only when live Hermes APIs are unavailable. This intentionally avoids
    shipping a static hardcoded model list so the picker reflects this install's
    real config/history instead of a synthetic catalog.
    """
    providers_dict: dict[str, list[str]] = {}

    # Seed from configured tiers in router config.
    try:
        cfg_path = default_config_path()
        if cfg_path.exists():
            cfg_data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            for tier in cfg_data.get("tiers", []) or []:
                if not isinstance(tier, dict):
                    continue
                for slot in ("primary", "fallback", "secondary_fallback"):
                    model_entry = tier.get(slot)
                    if not isinstance(model_entry, dict):
                        continue
                    provider = str(model_entry.get("provider", "") or "").strip()
                    model = str(model_entry.get("model", "") or "").strip()
                    if not provider or not model:
                        continue
                    _merge_provider_models(providers_dict, provider, [model])
                for model_entry in tier.get("candidates", []) or tier.get("additional_candidates", []) or []:
                    if not isinstance(model_entry, dict):
                        continue
                    provider = str(model_entry.get("provider", "") or "").strip()
                    model = str(model_entry.get("model", "") or "").strip()
                    if not provider or not model:
                        continue
                    _merge_provider_models(providers_dict, provider, [model])
    except Exception:
        pass

    # Augment with any real data from routing history (excluding local providers).
    try:
        from pathlib import Path
        db_path = Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_state.db"
        
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            rows = conn.execute("""
                SELECT DISTINCT selected_provider, selected_model 
                FROM routing_runs 
                WHERE selected_provider IS NOT NULL 
                ORDER BY selected_provider
            """).fetchall()
            
            local_only_providers = {"ollama", "local", "localhost"}
            for provider, model in rows:
                if provider and model:
                    provider_lower = str(provider).lower()
                    if provider_lower not in local_only_providers:
                        _merge_provider_models(providers_dict, str(provider), [str(model)])

            fallback_rows = conn.execute("""
                SELECT DISTINCT fallback_provider, fallback_model
                FROM routing_runs
                WHERE fallback_provider IS NOT NULL AND fallback_model IS NOT NULL
                ORDER BY fallback_provider
            """).fetchall()
            for provider, model in fallback_rows:
                if provider and model:
                    provider_lower = str(provider).lower()
                    if provider_lower not in local_only_providers:
                        _merge_provider_models(providers_dict, str(provider), [str(model)])
            
            conn.close()
    except Exception:
        pass

    return providers_dict


def _get_hermes_provider_models_from_db() -> dict[str, list[str]]:
    """Legacy: Extract provider/model info from routing history database.
    
    Used when Hermes CLI is not available. Returns most recent models used.
    Filters out local-only providers.
    """
    try:
        from pathlib import Path
        db_path = Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_state.db"
        
        if not db_path.exists():
            return {}
        
        conn = sqlite3.connect(db_path)
        
        # Get unique providers/models used in recent routing decisions
        rows = conn.execute("""
            SELECT DISTINCT 
                selected_provider as provider, 
                selected_model as model
            FROM routing_runs 
            ORDER BY id DESC 
            LIMIT 100
        """).fetchall()
        
        providers_dict: dict[str, list[str]] = {}
        local_only = {"ollama", "local", "localhost"}
        
        for provider, model in rows:
            if provider and model:
                provider_lower = str(provider).lower()
                # Skip local-only providers
                if provider_lower not in local_only:
                    if provider not in providers_dict:
                        providers_dict[provider] = []
                    if model not in providers_dict[provider]:
                        providers_dict[provider].append(model)
        
        # Also get fallback models
        rows = conn.execute("""
            SELECT DISTINCT 
                fallback_provider as provider, 
                fallback_model as model
            FROM routing_runs 
            WHERE fallback_provider IS NOT NULL
            ORDER BY id DESC 
            LIMIT 50
        """).fetchall()
        
        for provider, model in rows:
            if provider and model:
                provider_lower = str(provider).lower()
                # Skip local-only providers
                if provider_lower not in local_only:
                    if provider not in providers_dict:
                        providers_dict[provider] = []
                    if model not in providers_dict[provider]:
                        providers_dict[provider].append(model)
        
        conn.close()
        return providers_dict
    except Exception:
        return {}


def _build_model_cost_lookup(cfg) -> dict[tuple[str, str], float]:
    """Build a quick lookup of configured model costs by provider/model.

    Includes both router tier costs and numeric costs from pricing catalog.
    """
    lookup: dict[tuple[str, str], float] = {}
    for tier in cfg.tiers:
        for model in _iter_tier_models(tier):
            if not model:
                continue
            key = (_provider_slug(model.provider), str(model.model).strip().lower())
            lookup[key] = float(model.estimated_cost_per_1k)

    catalog = _load_pricing_catalog(default_pricing_catalog_path())
    for row in catalog.get("models", []):
        provider = _provider_slug(str(row.get("provider", "") or ""))
        model = str(row.get("model", "") or "").strip().lower()
        if not provider or not model:
            continue
        try:
            cost = row.get("estimated_cost_per_1k")
            if cost is None:
                continue
            lookup[(provider, model)] = float(cost)
        except Exception:
            continue
    return lookup


def _provider_lookup_keys(provider_name: str) -> list[str]:
    """Return normalized provider keys for matching display names to IDs."""
    return _runtime_provider_keys(provider_name)


def _suggest_pricing_equivalent(
    provider_name: str,
    model_name: str,
    cost_lookup: dict[tuple[str, str], float],
) -> tuple[str, float, str] | None:
    provider_keys = _provider_lookup_keys(provider_name)
    model_key = str(model_name or "").strip().lower()
    if not model_key:
        return None

    # Prefer suggestions from the same provider namespace.
    provider_candidates: list[tuple[str, float, str]] = []
    global_candidates: list[tuple[str, float, str]] = []
    for (provider, model), cost in cost_lookup.items():
        record = (model, float(cost), provider)
        if provider in provider_keys:
            provider_candidates.append(record)
        global_candidates.append(record)

    def _pick(candidates: list[tuple[str, float, str]]) -> tuple[str, float, str] | None:
        if not candidates:
            return None
        names = [name for name, _, _ in candidates]
        close = difflib.get_close_matches(model_key, names, n=1, cutoff=0.45)
        if close:
            match = close[0]
            for name, cost, provider in candidates:
                if name == match:
                    return name, cost, provider

        # Fallback heuristic: same family prefix.
        family = model_key.split("-")[0]
        family_hits = [row for row in candidates if row[0].startswith(family + "-")]
        if family_hits:
            family_hits.sort(key=lambda row: row[1])
            return family_hits[0]
        return None

    return _pick(provider_candidates) or _pick(global_candidates)


def _show_pricing_gaps(cfg) -> None:
    """Show visible models missing pricing with best-effort suggested equivalents."""
    _clear_screen()
    width = 120
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "PRICING GAPS & SUGGESTED EQUIVALENTS".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")

    providers_data = _get_hermes_provider_models()
    cost_lookup = _build_model_cost_lookup(cfg)

    missing_rows: list[str] = []
    for provider_name, models in sorted(providers_data.items()):
        for model in sorted(models):
            cost = None
            for provider_key in _provider_lookup_keys(provider_name):
                cost = cost_lookup.get((provider_key, model.strip().lower()))
                if cost is not None:
                    break
            if cost is not None:
                continue

            suggestion = _suggest_pricing_equivalent(provider_name, model, cost_lookup)
            if suggestion is None:
                row = f"{provider_name}/{model} -> no suggestion"
            else:
                s_model, s_cost, s_provider = suggestion
                row = (
                    f"{provider_name}/{model} -> suggested {s_provider}/{s_model} "
                    f"(${s_cost:.5f}/1k)"
                )
            missing_rows.append(row)

    if not missing_rows:
        print(f"│ All visible models currently have pricing entries.{' ' * (width - 52)}│")
    else:
        header = f"Missing prices: {len(missing_rows)} models"
        print(f"│ {header:<{width-4}}│")
        print("├" + "─" * (width - 2) + "┤")
        for row in missing_rows[:80]:
            text = row
            if len(text) > width - 4:
                text = text[: width - 7] + "..."
            print(f"│ {text:<{width-4}}│")

    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")


def _show_full_prompt(item: dict, cfg) -> None:
    """Display full prompt with actual Hermes routing context."""
    _clear_screen()
    width = 120
    
    # Determine source of model discovery
    source_label = "Live Hermes Runtime"
    try:
        rt = _get_hermes_provider_models_via_runtime()
        if not rt:
            source_label = "Fallback (Config/History)"
    except Exception:
        source_label = "Fallback (Config/History)"
    
    print(f"[Model Discovery Source: {source_label}]\n")
    
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "FULL PROMPT & ROUTING CONTEXT".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")
    
    # User prompt (full, wrapped; no truncation)
    prompt_text = item.get("prompt_text") or item.get("prompt_preview", "")
    print("│ USER ASKED:".ljust(width - 1) + "│")
    _print_box_wrapped(prompt_text, width=width, indent="  ")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ ROUTER SYSTEM PROMPT:".ljust(width - 1) + "│")
    system_prompt = (
        "Choose the best available LLM from current Hermes providers."
        " Optimize for: cost-efficiency, response quality, availability."
    )
    _print_box_wrapped(system_prompt, width=width, indent="  ")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ AVAILABLE MODELS IN HERMES (ALL - NO TRUNCATION):".ljust(width - 1) + "│")
    
    # Get actual Hermes providers and models
    providers_data = _get_hermes_provider_models()
    cost_lookup = _build_model_cost_lookup(cfg)
    
    if providers_data:
        for provider_name, models in sorted(providers_data.items()):
            print(f"│ {provider_name} ({len(models)} models)".ljust(width - 1) + "│")
            # Show ALL models without truncation
            for model in sorted(models):
                cost = None
                for provider_key in _provider_lookup_keys(provider_name):
                    cost = cost_lookup.get((provider_key, model.strip().lower()))
                    if cost is not None:
                        break
                if cost is None:
                    model_line = f"    • {model}  ($N/A)"
                else:
                    model_line = f"    • {model}  (${cost:.5f}/1k)"
                _print_box_wrapped(model_line, width=width)
    else:
        print("│   [Could not fetch live Hermes provider list]".ljust(width - 1) + "│")

    print("├" + "─" * (width - 2) + "┤")
    print("│ TIER MODEL TABLE (PRIMARY + COUNTERPARTS):".ljust(width - 1) + "│")

    tier_catalog = _load_pricing_catalog(default_pricing_catalog_path())
    tier_catalog, _, _ = _enrich_pricing_catalog_with_visible_models(cfg, tier_catalog)
    tier_table = _build_tier_model_catalog(cfg, tier_catalog)

    for tier_name in ["T1", "T2", "T3", "T4", "T5"]:
        _print_box_wrapped(f"{tier_name}", width=width, indent="  ")
        rows = (tier_table.get("tiers", {}) or {}).get(tier_name, []) or []
        if not rows:
            _print_box_wrapped("- no models", width=width, indent="    ")
            continue

        for row in rows:
            primary = row.get("primary", {})
            p_price = primary.get("price_per_1k")
            p_price_text = "N/A" if p_price is None else f"${float(p_price):.5f}/1k"
            p_strength = primary.get("strength", "-")
            _print_box_wrapped(
                f"Primary: {primary.get('provider', '?')}/{primary.get('model', '?')} | {p_price_text} | {p_strength}",
                width=width,
                indent="    ",
            )

            for cp in row.get("counterparts", []) or []:
                cp_price = cp.get("price_per_1k")
                cp_price_text = "N/A" if cp_price is None else f"${float(cp_price):.5f}/1k"
                cp_strength = cp.get("strength", "-")
                _print_box_wrapped(
                    f"Counterpart: {cp.get('provider', '?')}/{cp.get('model', '?')} | {cp_price_text} | {cp_strength}",
                    width=width,
                    indent="      ",
                )
    
    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")





def _show_reasoning(item: dict) -> None:
    """Display routing decision reasoning with detailed metadata."""
    _clear_screen()
    width = 80
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "ROUTING DECISION REASONING".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")
    
    # Decision Metadata
    print("│ DECISION METADATA:".ljust(width - 1) + "│")
    confidence = item.get('confidence', 0)
    mode = item.get('routing_mode', 'unknown')
    tier = item.get('tier_equivalent', 'unknown')
    cost = item.get('estimated_cost', 0.0)
    
    metadata_lines = [
        f"  Confidence: {confidence}%",
        f"  Mode: {mode}",
        f"  Tier: {tier}",
        f"  Estimated Cost: ${cost:.4f}",
    ]
    for line in metadata_lines:
        if len(line) > width - 6:
            line = line[:width - 9] + "..."
        print(f"│ {line:<{width-4}}│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ ROUTING REASONING:".ljust(width - 1) + "│")
    
    reason = item.get("routing_reason", "No reasoning available")
    for line in reason.split('\n'):
        if line.strip():
            # Wrap long lines properly
            while len(line) > width - 6:
                chunk = line[:width - 9]
                print(f"│   {chunk:<{width-6}}│")
                line = line[width - 9:]
            if line:
                print(f"│   {line:<{width-6}}│")
        else:
            print("│" + " " * (width - 2) + "│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ SELECTION DETAILS:".ljust(width - 1) + "│")
    
    selected_provider = item.get("selected_provider", "?")
    selected_model = item.get("selected_model", "?")
    selection_lines = [
        f"  Selected: {selected_provider}/{selected_model}",
    ]
    
    if item.get("fallback_provider"):
        fallback_provider = item.get("fallback_provider", "?")
        fallback_model = item.get("fallback_model", "?")
        selection_lines.append(f"  Fallback: {fallback_provider}/{fallback_model}")
    
    selection_lines.append("  Fallback triggers when selected unavailable")
    
    for line in selection_lines:
        if len(line) > width - 6:
            line = line[:width - 9] + "..."
        print(f"│ {line:<{width-4}}│")
    
    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")


def _show_smart_routing_scores(item: dict, cfg, store: RouterStateStore) -> None:
    """Display per-candidate smart-auto score breakdown for the current prompt."""
    _clear_screen()
    width = 120

    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "SMART ROUTING SCORE BREAKDOWN".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")

    prompt_text = item.get("prompt_text") or item.get("prompt_preview", "")
    if not prompt_text:
        prompt_text = "[prompt not available]"
    prompt_preview = prompt_text.replace("\n", " ")
    if len(prompt_preview) > width - 8:
        prompt_preview = prompt_preview[: width - 11] + "..."

    mode = item.get("routing_mode", "unknown")
    selected = f"{item.get('selected_provider', '?')}/{item.get('selected_model', '?')}"
    print(f"│ Prompt: {prompt_preview:<{width-11}}│")
    print(f"│ Decision Mode: {mode:<{width-18}}│")
    print(f"│ Selected: {selected:<{width-12}}│")
    print("├" + "─" * (width - 2) + "┤")

    if mode != "smart_auto":
        print(f"│ Note: This run used '{mode}', not smart_auto. Showing simulated smart_auto scores for this prompt.{' ' * 10}│")
        print("├" + "─" * (width - 2) + "┤")

    request = RoutingRequest(prompt=prompt_text)

    provider_states = store.load_provider_states([
        {
            "id": provider.id,
            "name": provider.name,
            "type": provider.type.value,
            "standby_only": provider.standby_only,
        }
        for provider in cfg.providers
        if provider.enabled
    ])

    try:
        from .plugin import _load_available_model_catalog

        available_catalog = _load_available_model_catalog()
    except Exception:
        available_catalog = {}

    candidates = collect_candidate_models(cfg)
    candidates = _filter_candidates_by_available_models(candidates, available_catalog)
    candidates = _filter_candidates_for_provider_rules(candidates, provider_states)
    flexibility_scores = provider_flexibility_scores(candidates)
    positive_costs = [c.estimated_cost_per_1k for c in candidates if c.estimated_cost_per_1k > 0]
    cheapest_cost = min(positive_costs) if positive_costs else 0.0

    if not candidates:
        print(f"│ No candidates available after provider/model filters.{' ' * (width - 50)}│")
        print("╰" + "─" * (width - 2) + "╯")
        input("\nPress Enter to return to menu...")
        return

    scored_rows: list[tuple[float, str]] = []
    for candidate in candidates:
        state = provider_states.get(candidate.provider)
        if not state:
            continue
        if state.status not in {
            ProviderHealthStatus.AVAILABLE,
            ProviderHealthStatus.LIMITED,
            ProviderHealthStatus.STANDBY,
        }:
            continue

        task_fit = _task_fit_score(request, candidate)
        capability = _capability_score(candidate)
        health = 15.0 if state.status == ProviderHealthStatus.AVAILABLE else 8.0
        quota = 10.0 if state.estimated_remaining is None else min(10.0, state.estimated_remaining / 10)
        preservation = max(0.0, 10.0 - flexibility_scores.get(candidate.provider, 10.0))
        latency = max(0.0, 12.0 - (candidate.latency_ms_estimate / 250.0))
        cost_penalty = _cost_penalty(request, candidate, cheapest_cost)
        overkill_penalty = _overkill_penalty(request, candidate)
        underfit_penalty = _underfit_penalty(request, candidate)
        failure_risk = state.failure_rate * 10.0

        total = (
            task_fit
            + capability
            + health
            + quota
            + preservation
            + latency
            - cost_penalty
            - failure_risk
            - overkill_penalty
            - underfit_penalty
        )

        line = (
            f"{candidate.provider}/{candidate.model} | total={total:6.2f} | "
            f"fit={task_fit:4.1f} cap={capability:4.1f} health={health:4.1f} quota={quota:4.1f} "
            f"pres={preservation:4.1f} lat={latency:4.1f} "
            f"cost-={cost_penalty:5.2f} over-={overkill_penalty:4.1f} under-={underfit_penalty:4.1f} "
            f"fail-={failure_risk:4.1f}"
        )
        scored_rows.append((total, line))

    if not scored_rows:
        print(f"│ No healthy candidates available for scoring.{' ' * (width - 43)}│")
        print("╰" + "─" * (width - 2) + "╯")
        input("\nPress Enter to return to menu...")
        return

    scored_rows.sort(key=lambda row: row[0], reverse=True)
    print(f"│ {'Candidate Scores (highest first)':<{width-4}} │")
    print("├" + "─" * (width - 2) + "┤")

    for idx, (_, row_text) in enumerate(scored_rows, start=1):
        prefix = f"#{idx:02d} "
        text = prefix + row_text
        if len(text) > width - 4:
            text = text[: width - 7] + "..."
        print(f"│ {text:<{width-4}}│")

    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")


def _show_available_models(cfg) -> None:
    """Display actual Hermes providers and tier configuration."""
    _clear_screen()
    width = 80
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "AVAILABLE PROVIDERS & TIER CONFIGURATION".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")
    
    print("│ LIVE HERMES PROVIDERS (with model counts):".ljust(width - 1) + "│")
    
    # Get actual Hermes providers and models
    providers_data = _get_hermes_provider_models()
    
    if providers_data:
        for provider_name, models in sorted(providers_data.items()):
            model_count = len(models)
            line = f"  • {provider_name:<25} ({model_count} models)"
            if len(line) > width - 6:
                line = line[:width - 9] + "..."
            print(f"│ {line:<{width-4}}│")
    else:
        print("│   [Could not fetch live Hermes providers - check Hermes connectivity]".ljust(width - 1) + "│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ ROUTER TIER STRUCTURE (Primary Models):".ljust(width - 1) + "│")
    
    tier_lines = []
    for tier in cfg.tiers:
        if tier.primary:
            line = f"  {tier.tier}: {tier.primary.provider}/{tier.primary.model}"
            if len(line) > width - 6:
                line = line[:width - 9] + "..."
            tier_lines.append(line)
    
    if not tier_lines:
        tier_lines = ["  (No tiers configured)"]
    
    for line in tier_lines:
        print(f"│ {line:<{width-4}}│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ ROUTER CONFIGURATION:".ljust(width - 1) + "│")
    
    enabled_count = sum(1 for p in cfg.providers if p.enabled)
    total_count = len(cfg.providers)
    line = f"  Providers in config: {enabled_count} enabled, {total_count - enabled_count} disabled"
    print(f"│ {line:<{width-4}}│")
    
    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")





def _show_settings(cfg) -> None:
    """Display router configuration settings with detailed information."""
    _clear_screen()
    width = 80
    print("╭" + "─" * (width - 2) + "╮")
    print("│ " + "ROUTER CONFIGURATION SETTINGS".ljust(width - 4) + " │")
    print("╠" + "─" * (width - 2) + "╣")
    
    settings = cfg.settings
    
    # Core Settings
    print("│ CORE ROUTING SETTINGS:".ljust(width - 1) + "│")
    core_settings = [
        ("Routing Mode", settings.routing_mode.value),
        ("Confidence Threshold", f"{settings.confidence_threshold}%"),
        ("Provider Preservation", "Enabled" if settings.provider_preservation_enabled else "Disabled"),
    ]
    for key, value in core_settings:
        line = f"  {key:<30} {value}"
        if len(line) > width - 6:
            line = line[:width - 9] + "..."
        print(f"│ {line:<{width-4}}│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ FALLBACK & API SETTINGS:".ljust(width - 1) + "│")
    fallback_settings = [
        ("Auto Fallback to Tier", "Enabled" if settings.auto_fallback_to_tier else "Disabled"),
        ("Allow API Fallback", "Enabled" if settings.allow_api_fallback else "Disabled"),
    ]
    for key, value in fallback_settings:
        line = f"  {key:<30} {value}"
        if len(line) > width - 6:
            line = line[:width - 9] + "..."
        print(f"│ {line:<{width-4}}│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ DATA & TRACKING SETTINGS:".ljust(width - 1) + "│")
    tracking_settings = [
        ("Cost Tracking", "Enabled" if settings.cost_tracking_enabled else "Disabled"),
        ("Full Prompt Logging", "Enabled" if settings.store_full_prompts_for_debug else "Disabled"),
        ("History Retention", f"{settings.routing_history_retention_days} days"),
    ]
    for key, value in tracking_settings:
        line = f"  {key:<30} {value}"
        if len(line) > width - 6:
            line = line[:width - 9] + "..."
        print(f"│ {line:<{width-4}}│")
    
    print("├" + "─" * (width - 2) + "┤")
    print("│ PROVIDER CONFIGURATION:".ljust(width - 1) + "│")
    enabled_count = sum(1 for p in cfg.providers if p.enabled)
    total_count = len(cfg.providers)
    line = f"  Enabled Providers: {enabled_count}/{total_count}"
    print(f"│ {line:<{width-4}}│")
    
    tier_count = len(cfg.tiers)
    line = f"  Configured Tiers: {tier_count}"
    print(f"│ {line:<{width-4}}│")
    
    print("╰" + "─" * (width - 2) + "╯")
    input("\nPress Enter to return to menu...")



def _print_monitor_view(history: list[dict], snapshot: dict, limit: int, full_prompt: bool) -> None:
    """Print historical view of routing runs."""
    _clear_screen()
    print("HERMES SMART ROUTER MONITOR - Historical View")
    print(f"Showing latest {min(limit, len(history))} routing runs\n")
    if snapshot:
        print(
            "Runs: "
            f"{snapshot.get('run_count', 0)} | "
            f"Smart: {snapshot.get('smart_auto_runs', 0)} | "
            f"Tier: {snapshot.get('tier_runs', 0)} | "
            f"Estimated spend: ${snapshot.get('estimated_api_spend', 0.0)}\n"
        )

    for item in reversed(history[-limit:]):
        print("-" * 80)
        print(f"Time: {item.get('timestamp', 'unknown')}")
        prompt_text = item.get("prompt_text") or ""
        prompt = prompt_text if full_prompt else item.get("prompt_preview")
        if full_prompt and not prompt_text:
            prompt = "[full prompt logging disabled]"
        print(f"Prompt: {prompt}")
        print(
            "Selected: "
            f"{item.get('selected_provider', 'none')} "
            f"{item.get('selected_model', 'none')}"
        )
        if item.get("fallback_provider"):
            print(
                "Fallback: "
                f"{item.get('fallback_provider')} "
                f"{item.get('fallback_model')}"
            )
        print(
            "Mode/Tier/Confidence: "
            f"{item.get('routing_mode', 'unknown')} / "
            f"{item.get('tier_equivalent', 'unknown')} / "
            f"{item.get('confidence', 0)}"
        )
        print(f"Estimated cost: {item.get('estimated_cost', 0.0)}")
        print(f"Reason: {item.get('routing_reason', '')}")


def cmd_monitor(config_path: Path, limit: int, follow: bool, interval: float, full_prompt: bool) -> int:
    """Interactive monitor with menu-driven views."""
    cfg = load_router_config(config_path)
    store = RouterStateStore(
        config_path.parent,
        history_retention_days=cfg.settings.routing_history_retention_days,
        persist_full_prompts=cfg.settings.store_full_prompts_for_debug,
    )
    
    db_path = store.db_path

    def render_once() -> None:
        history = store.load_history()
        snapshot = store.load_cost_snapshot()
        _print_monitor_view(history=history, snapshot=snapshot, limit=limit, full_prompt=full_prompt)

    if not follow:
        render_once()
        return 0

    try:
        latest_id = _get_max_routing_id(db_path)
        
        print("⚕ HERMES SMART ROUTER MONITOR")
        print("Waiting for new routing decisions... Press Ctrl+C to stop.\n")
        
        while True:
            new_items = _get_new_routing_decisions(db_path, latest_id, limit=100)
            
            if new_items:
                for item in new_items:
                    latest_id = max(latest_id, item.get("id", latest_id))
                    
                    # Display the routing decision
                    _print_routing_decision(item)
                    
                    # Refresh config on each new event to avoid stale settings/costs
                    cfg = load_router_config(config_path)

                    # Interactive menu loop
                    while True:
                        choice = _show_menu()
                        
                        if choice == "1":
                            _show_full_prompt(item, cfg)
                        elif choice == "2":
                            _show_reasoning(item)
                        elif choice == "3":
                            _show_smart_routing_scores(item, cfg, store)
                        elif choice == "4":
                            _show_pricing_gaps(cfg)
                        elif choice == "5":
                            _show_available_models(cfg)
                        elif choice == "6":
                            _show_settings(cfg)
                        elif choice == "7":
                            break
                    
                    # Back to main monitor display
                    print("\n⚕ HERMES SMART ROUTER MONITOR")
                    print("Waiting for new routing decisions... Press Ctrl+C to stop.\n")
            
            time.sleep(max(interval, 0.5))
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")
        return 0


def cmd_debug_provider_payload(verbose: bool = False) -> int:
    """Print raw provider discovery payload from Hermes runtime."""
    _clear_screen()
    print("\n┌─ Provider Discovery Payload (Raw) ──────────────────────────────┐")
    print("│ Source: Live Hermes Runtime                                     │")
    print("└──────────────────────────────────────────────────────────────────┘\n")
    
    live = _get_hermes_provider_models_via_runtime()
    if live:
        for provider, models in sorted(live.items()):
            print(f"Provider: {provider}")
            print(f"  Count: {len(models)}")
            if verbose:
                print(f"  Models: {sorted(models)}")
            else:
                sample = sorted(models)[:5]
                print(f"  Models: {sample} ... (showing first 5, use --verbose for all)")
            print()
    else:
        print("[No live data - using fallback]\n")
        fallback = _get_hermes_provider_catalog_fallback()
        for provider, models in sorted(fallback.items()):
            print(f"Provider: {provider}")
            print(f"  Count: {len(models)}")
            if verbose:
                print(f"  Models: {sorted(models)}")
            else:
                sample = sorted(models)[:5]
                print(f"  Models: {sample} ... (showing first 5, use --verbose for all)")
            print()
    
    input("Press Enter to return...")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-smart-router")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to router config yaml",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Create/migrate config and prepare defaults")
    sub.add_parser("doctor", help="Run baseline diagnostics")
    sub.add_parser("status", help="Show provider health, routing history, and cost snapshot")
    monitor = sub.add_parser("monitor", help="Show routing monitor output for debugging")
    monitor.add_argument("--limit", type=int, default=20, help="Number of recent routing runs to display")
    monitor.add_argument("--follow", action="store_true", help="Refresh monitor output continuously")
    monitor.add_argument("--interval", type=float, default=2.0, help="Seconds between refreshes in follow mode")
    monitor.add_argument("--full-prompt", action="store_true", help="Show full prompt text instead of preview")

    pricing_init = sub.add_parser("pricing-init", help="Create or refresh a pricing catalog from current config")
    pricing_init.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    pricing_init.add_argument("--force", action="store_true", help="Overwrite existing catalog")

    pricing_report = sub.add_parser("pricing-report", help="Report pricing coverage and staleness")
    pricing_report.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    pricing_report.add_argument("--stale-days", type=int, default=7, help="Mark catalog stale if older than this")

    pricing_sync = sub.add_parser("pricing-sync", help="Apply catalog prices to router tier model costs")
    pricing_sync.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    pricing_sync.add_argument("--dry-run", action="store_true", help="Compute changes without writing config")

    pricing_refresh = sub.add_parser("pricing-refresh", help="Run scheduled pricing refresh command when due")
    pricing_refresh.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    pricing_refresh.add_argument("--force", action="store_true", help="Run refresh even if catalog is not due yet")
    pricing_refresh.add_argument(
        "--refresh-command",
        type=str,
        default="",
        help="Optional shell command that updates pricing catalog from web/LLM sources",
    )

    pricing_backfill = sub.add_parser(
        "pricing-backfill",
        help="Ensure pricing catalog contains all visible models and infer missing prices from equivalents",
    )
    pricing_backfill.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    pricing_backfill.add_argument("--dry-run", action="store_true", help="Compute changes without writing catalog")

    tier_table = sub.add_parser(
        "tier-table-build",
        help="Build weekly tier model table (yaml+markdown) with primary/counterpart rows",
    )
    tier_table.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    tier_table.add_argument("--output", type=Path, default=default_tier_catalog_path(), help="Output path for tier model catalog yaml")
    tier_table.add_argument("--no-backfill", action="store_true", help="Skip pricing backfill before building tier table")
    tier_table.add_argument("--dry-run", action="store_true", help="Compute output summary without writing files")

    debug = sub.add_parser("debug-providers", help="Show raw provider discovery payload from Hermes")
    debug.add_argument("--verbose", action="store_true", help="Show all models (default: first 5 per provider)")

    expand = sub.add_parser("expand-tiers", help="Expand tier configuration to include all discovered models")
    expand.add_argument("--catalog", type=Path, default=default_pricing_catalog_path(), help="Path to pricing catalog yaml")
    expand.add_argument("--dry-run", action="store_true", help="Show what would be added without modifying config")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        return cmd_setup(args.config)
    if args.command == "doctor":
        return cmd_doctor(args.config)
    if args.command == "status":
        return cmd_status(args.config)
    if args.command == "monitor":
        return cmd_monitor(
            config_path=args.config,
            limit=args.limit,
            follow=args.follow,
            interval=args.interval,
            full_prompt=args.full_prompt,
        )
    if args.command == "pricing-init":
        return cmd_pricing_init(config_path=args.config, catalog_path=args.catalog, force=args.force)
    if args.command == "pricing-report":
        return cmd_pricing_report(config_path=args.config, catalog_path=args.catalog, stale_days=args.stale_days)
    if args.command == "pricing-sync":
        return cmd_pricing_sync(config_path=args.config, catalog_path=args.catalog, dry_run=args.dry_run)
    if args.command == "pricing-refresh":
        cmd = args.refresh_command.strip() if isinstance(args.refresh_command, str) else ""
        return cmd_pricing_refresh(catalog_path=args.catalog, refresh_command=cmd or None, force=bool(args.force))
    if args.command == "pricing-backfill":
        return cmd_pricing_backfill(config_path=args.config, catalog_path=args.catalog, dry_run=bool(args.dry_run))
    if args.command == "tier-table-build":
        return cmd_tier_table_build(
            config_path=args.config,
            catalog_path=args.catalog,
            output_path=args.output,
            backfill_pricing=not bool(args.no_backfill),
            dry_run=bool(args.dry_run),
        )
    if args.command == "debug-providers":
        return cmd_debug_provider_payload(verbose=bool(args.verbose))
    if args.command == "expand-tiers":
        return cmd_expand_tiers(config_path=args.config, catalog_path=args.catalog, dry_run=bool(args.dry_run))

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
