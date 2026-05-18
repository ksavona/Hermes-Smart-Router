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


def _default_catalog_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "pricing_catalog.yaml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"metadata": {}, "models": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Pricing catalog must be a YAML object.")
    data.setdefault("metadata", {})
    data.setdefault("models", [])
    if not isinstance(data["metadata"], dict):
        data["metadata"] = {}
    if not isinstance(data["models"], list):
        data["models"] = []
    return data


def _save_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")


def _key(provider: str, model: str) -> tuple[str, str]:
    return (str(provider).strip().lower(), str(model).strip().lower())


def _extract_json_block(text: str) -> str:
    raw = text.strip()
    if not raw:
        raise ValueError("No output received from updater source.")

    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1)

    first_brace = raw.find("{")
    first_bracket = raw.find("[")
    starts = [idx for idx in (first_brace, first_bracket) if idx >= 0]
    if not starts:
        raise ValueError("Updater output does not contain JSON.")
    start = min(starts)
    return raw[start:]


def _normalize_updates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "updates" in payload and isinstance(payload["updates"], list):
            return [row for row in payload["updates"] if isinstance(row, dict)]
        if {"provider", "model"}.issubset(set(payload.keys())):
            return [payload]
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _build_prompt(catalog: dict[str, Any]) -> str:
    models = catalog.get("models", [])
    lines = []
    for row in models:
        provider = str(row.get("provider", "")).strip()
        model = str(row.get("model", "")).strip()
        if provider and model:
            lines.append(f"- {provider}/{model}")

    joined = "\n".join(lines)
    return (
        "You are updating model pricing for Hermes Smart Router.\n"
        "Use official provider pricing pages and return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "updates": [\n'
        "    {\n"
        '      "provider": "copilot",\n'
        '      "model": "gpt-5-mini",\n'
        '      "estimated_cost_per_1k": 0.00001,\n'
        '      "source_url": "https://...",\n'
        f'      "verified_at": "{_now_iso()}",\n'
        '      "confidence": "high"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Only include models with confident pricing.\n"
        "Models to check:\n"
        f"{joined}\n"
    )


def _run_llm_command(command: str, prompt: str) -> str:
    proc = subprocess.run(command, shell=True, text=True, input=prompt, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"LLM command failed with code {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    output = proc.stdout.strip()
    if not output:
        raise RuntimeError("LLM command returned empty output.")
    return output


def _load_updates_from_json_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_updates(payload)


def _parse_updates_from_output(text: str) -> list[dict[str, Any]]:
    block = _extract_json_block(text)
    payload = json.loads(block)
    return _normalize_updates(payload)


def _to_float(value: Any) -> float:
    if value is None:
        raise ValueError("cost is missing")
    return float(value)


def _is_http_url(value: str) -> bool:
    s = str(value or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def _apply_updates(catalog: dict[str, Any], updates: list[dict[str, Any]], strict: bool) -> tuple[int, int, int]:
    models = catalog.get("models", [])
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in models:
        provider = row.get("provider")
        model = row.get("model")
        if provider and model:
            index[_key(provider, model)] = row

    updated = 0
    skipped = 0
    added = 0

    for row in updates:
        provider = str(row.get("provider", "")).strip()
        model = str(row.get("model", "")).strip()
        if not provider or not model:
            skipped += 1
            continue

        try:
            cost = _to_float(row.get("estimated_cost_per_1k"))
            if cost < 0:
                raise ValueError("cost must be >= 0")
        except Exception:
            skipped += 1
            continue

        source_url = str(row.get("source_url", "")).strip()
        if source_url and not _is_http_url(source_url):
            skipped += 1
            continue

        verified_at = str(row.get("verified_at", "")).strip() or _now_iso()
        confidence = str(row.get("confidence", "medium")).strip().lower() or "medium"
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"

        k = _key(provider, model)
        existing = index.get(k)
        if existing is None:
            if strict:
                skipped += 1
                continue
            existing = {
                "provider": provider,
                "model": model,
                "estimated_cost_per_1k": cost,
                "source_url": source_url,
                "verified_at": verified_at,
                "confidence": confidence,
            }
            models.append(existing)
            index[k] = existing
            added += 1
            continue

        existing["estimated_cost_per_1k"] = cost
        existing["source_url"] = source_url
        existing["verified_at"] = verified_at
        existing["confidence"] = confidence
        updated += 1

    return updated, added, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Hermes pricing catalog from LLM/web JSON output.")
    parser.add_argument("--catalog", type=Path, default=_default_catalog_path(), help="Path to pricing_catalog.yaml")
    parser.add_argument(
        "--llm-command",
        type=str,
        default="",
        help="Shell command to run a web-enabled LLM. Prompt is passed via stdin. Command must return JSON.",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        default=None,
        help="Path to JSON file with pricing updates (alternative to --llm-command).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Only update models already present in catalog; skip unknown models.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing catalog")
    args = parser.parse_args()

    if not args.llm_command and args.input_json is None:
        print("Provide one input source: --llm-command or --input-json", file=sys.stderr)
        return 2

    catalog = _load_catalog(args.catalog)

    try:
        if args.input_json is not None:
            updates = _load_updates_from_json_file(args.input_json)
        else:
            prompt = _build_prompt(catalog)
            output = _run_llm_command(args.llm_command, prompt)
            updates = _parse_updates_from_output(output)
    except Exception as exc:
        print(f"Failed to load updates: {exc}", file=sys.stderr)
        return 1

    if not updates:
        print("No valid updates found in input.")
        return 1

    updated, added, skipped = _apply_updates(catalog, updates, strict=args.strict)
    catalog.setdefault("metadata", {})
    catalog["metadata"]["updated_at"] = _now_iso()
    catalog["metadata"]["last_update_method"] = "input-json" if args.input_json is not None else "llm-command"

    if not args.dry_run:
        _save_catalog(args.catalog, catalog)

    print("Pricing catalog update summary")
    print(f"Catalog: {args.catalog}")
    print(f"Updates supplied: {len(updates)}")
    print(f"Updated existing entries: {updated}")
    print(f"Added new entries: {added}")
    print(f"Skipped invalid entries: {skipped}")
    print(f"Dry run: {'yes' if args.dry_run else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
