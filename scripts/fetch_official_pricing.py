#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml

OPENAI_PRICING_SOURCE = "https://openai.com/api/pricing/"
ANTHROPIC_PRICING_SOURCE = "https://www.anthropic.com/pricing"

OPENAI_MIRROR = "https://r.jina.ai/http://openai.com/api/pricing/"
ANTHROPIC_MIRROR = "https://r.jina.ai/http://www.anthropic.com/pricing"
OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"


def _default_catalog_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "pricing_catalog.yaml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Catalog not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Catalog YAML must be an object")
    data.setdefault("models", [])
    if not isinstance(data["models"], list):
        raise ValueError("Catalog models must be a list")
    return data


def _normalize_model_key(name: str) -> str:
    value = str(name or "").strip().lower()
    value = value.replace("_", "-")
    value = re.sub(r"\s+", "-", value)
    value = value.replace("gpt-5.4-mini", "gpt-5.4-mini")
    value = value.replace("gpt-5.4--mini", "gpt-5.4-mini")
    value = value.replace("mini", "mini")
    value = value.replace("sonnet-4-6", "sonnet-4.6")
    value = value.replace("claude-sonnet-46", "claude-sonnet-4.6")
    value = value.replace("claude-sonnet-4-6", "claude-sonnet-4.6")
    value = re.sub(r"[^a-z0-9\.-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def _run_curl(url: str) -> str:
    cmd = [
        "curl",
        "-A",
        "Mozilla/5.0",
        "-L",
        "--max-time",
        "30",
        url,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl failed for {url}")
    out = proc.stdout
    if not out.strip():
        raise RuntimeError(f"Empty response from {url}")
    return out


def _extract_openai_input_prices(markdown_text: str) -> dict[str, float]:
    prices: dict[str, float] = {}
    section_pattern = re.compile(r"^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    input_pattern = re.compile(r"Input:\s*\n\s*\$([0-9]+(?:\.[0-9]+)?)\s*/\s*1M\s*tokens", re.IGNORECASE)

    for match in section_pattern.finditer(markdown_text):
        title = match.group(1).strip()
        body = match.group(2)
        input_match = input_pattern.search(body)
        if not input_match:
            continue
        model_key = _normalize_model_key(title)
        per_1m = float(input_match.group(1))
        prices[model_key] = per_1m / 1000.0

    return prices


def _extract_anthropic_input_prices(markdown_text: str) -> dict[str, float]:
    prices: dict[str, float] = {}
    section_pattern = re.compile(r"^###\s+(.+?)\n(.*?)(?=^###\s+|\Z)", re.MULTILINE | re.DOTALL)
    input_pattern = re.compile(r"Input\s*\n\s*\$([0-9]+(?:\.[0-9]+)?)\s*/\s*M[Tt]ok", re.IGNORECASE)

    for match in section_pattern.finditer(markdown_text):
        title = match.group(1).strip()
        body = match.group(2)
        input_match = input_pattern.search(body)
        if not input_match:
            continue
        model_key = _normalize_model_key(f"claude-{title}")
        per_mtok = float(input_match.group(1))
        prices[model_key] = per_mtok / 1000.0

    return prices


def _extract_openrouter_input_prices(models_payload: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    if not isinstance(models_payload, dict):
        return prices
    data = models_payload.get("data")
    if not isinstance(data, list):
        return prices

    for row in data:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id", "") or "").strip().lower()
        pricing = row.get("pricing") or {}
        if not model_id or not isinstance(pricing, dict):
            continue

        prompt_price = pricing.get("prompt")
        if prompt_price in (None, ""):
            continue
        try:
            # OpenRouter pricing.prompt is USD per token.
            per_token = float(prompt_price)
            if per_token < 0:
                continue
            per_1k = per_token * 1000.0
        except Exception:
            continue

        short_name = model_id.split("/")[-1]
        prices[_normalize_model_key(short_name)] = per_1k

    return prices


def _model_price_from_sources(
    provider: str,
    model: str,
    openai_prices: dict[str, float],
    anthropic_prices: dict[str, float],
    openrouter_prices: dict[str, float],
    allow_proxy: bool,
) -> tuple[float | None, str, str]:
    provider_key = str(provider or "").strip().lower()
    model_key = _normalize_model_key(model)

    if model_key in openai_prices:
        confidence = "high" if provider_key in {"codex", "openai-codex"} else "medium"
        return openai_prices[model_key], OPENAI_PRICING_SOURCE, confidence

    if model_key in anthropic_prices:
        return anthropic_prices[model_key], ANTHROPIC_PRICING_SOURCE, "high"

    if model_key in openrouter_prices:
        # OpenRouter is useful as a public fallback reference, but not an
        # official provider price for Copilot/Codex billing.
        return openrouter_prices[model_key], OPENROUTER_MODELS_API, "low"

    if model_key.startswith("claude-sonnet") and "claude-sonnet-4.6" in anthropic_prices and allow_proxy:
        return anthropic_prices["claude-sonnet-4.6"], ANTHROPIC_PRICING_SOURCE, "low"

    if model_key == "gpt-5-mini" and "gpt-5.4-mini" in openai_prices and allow_proxy:
        return openai_prices["gpt-5.4-mini"], OPENAI_PRICING_SOURCE, "low"

    return None, "", ""


def _build_updates(
    catalog: dict[str, Any],
    openai_prices: dict[str, float],
    anthropic_prices: dict[str, float],
    openrouter_prices: dict[str, float],
    allow_proxy: bool,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    now = _now_iso()

    for row in catalog.get("models", []):
        provider = str(row.get("provider", "")).strip()
        model = str(row.get("model", "")).strip()
        if not provider or not model:
            continue

        price, source_url, confidence = _model_price_from_sources(
            provider,
            model,
            openai_prices,
            anthropic_prices,
            openrouter_prices,
            allow_proxy,
        )
        if price is None:
            continue

        updates.append(
            {
                "provider": provider,
                "model": model,
                "estimated_cost_per_1k": round(float(price), 8),
                "source_url": source_url,
                "verified_at": now,
                "confidence": confidence,
            }
        )

    return updates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch official pricing pages and generate JSON updates for update_pricing_catalog.py"
    )
    parser.add_argument("--catalog", type=Path, default=_default_catalog_path(), help="Path to pricing catalog yaml")
    parser.add_argument("--out-json", type=Path, default=None, help="Optional file path to write updates JSON")
    parser.add_argument("--allow-proxy", action="store_true", help="Allow best-effort proxy mapping for missing model names")
    parser.add_argument(
        "--use-openrouter",
        action="store_true",
        help="Use OpenRouter models API as low-confidence fallback for unmatched model prices",
    )
    args = parser.parse_args()

    try:
        catalog = _load_catalog(args.catalog)
    except Exception as exc:
        print(f"Failed to load catalog: {exc}", file=sys.stderr)
        return 1

    try:
        openai_text = _run_curl(OPENAI_MIRROR)
        anthropic_text = _run_curl(ANTHROPIC_MIRROR)
    except Exception as exc:
        print(f"Failed to fetch pricing pages: {exc}", file=sys.stderr)
        return 1

    openai_prices = _extract_openai_input_prices(openai_text)
    anthropic_prices = _extract_anthropic_input_prices(anthropic_text)
    openrouter_prices: dict[str, float] = {}
    if args.use_openrouter:
        try:
            openrouter_text = _run_curl(OPENROUTER_MODELS_API)
            openrouter_payload = json.loads(openrouter_text)
            openrouter_prices = _extract_openrouter_input_prices(openrouter_payload)
        except Exception:
            openrouter_prices = {}

    updates = _build_updates(catalog, openai_prices, anthropic_prices, openrouter_prices, args.allow_proxy)
    payload = {
        "updates": updates,
        "metadata": {
            "generated_at": _now_iso(),
            "openai_source": OPENAI_PRICING_SOURCE,
            "anthropic_source": ANTHROPIC_PRICING_SOURCE,
            "openrouter_source": OPENROUTER_MODELS_API if args.use_openrouter else "",
            "allow_proxy": bool(args.allow_proxy),
            "use_openrouter": bool(args.use_openrouter),
        },
    }

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote updates JSON: {args.out_json}")
        print(f"Updates count: {len(updates)}")
    else:
        print(json.dumps(payload, indent=2))

    if not updates:
        print("No matching model prices found. Consider running with --allow-proxy.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
