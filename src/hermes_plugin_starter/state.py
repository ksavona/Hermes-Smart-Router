from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .models import ProviderHealthStatus, ProviderState, RoutingDecision, RoutingMode, ProviderType


class RouterStateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.health_path = self.root / "provider_health.yaml"
        self.history_path = self.root / "routing_history.yaml"
        self.cost_path = self.root / "cost_snapshot.yaml"

    def load_provider_states(self, providers: list[dict[str, Any]]) -> dict[str, ProviderState]:
        raw = self._read_yaml(self.health_path).get("providers", {})
        states: dict[str, ProviderState] = {}
        for provider in providers:
            provider_id = provider["id"]
            saved = raw.get(provider_id, {})
            fallback = provider.get("type") == ProviderType.FALLBACK.value and provider.get("standby_only", False)
            states[provider_id] = ProviderState(
                provider_id=provider_id,
                provider_name=provider.get("name", provider_id),
                provider_type=ProviderType(provider.get("type", ProviderType.NORMAL.value)),
                status=ProviderHealthStatus(saved.get("status", "STANDBY" if fallback else "AVAILABLE")),
                quota_state=saved.get("quota_state", "unknown"),
                estimated_remaining=saved.get("estimated_remaining"),
                cooldown_until=_parse_dt(saved.get("cooldown_until")),
                next_probe_at=_parse_dt(saved.get("next_probe_at")),
                last_success_at=_parse_dt(saved.get("last_success_at")),
                last_failure_at=_parse_dt(saved.get("last_failure_at")),
                last_error_type=saved.get("last_error_type"),
                failure_rate=float(saved.get("failure_rate", 0.0)),
                timezone=saved.get("timezone", "UTC"),
            )
        return states

    def save_provider_states(self, provider_states: dict[str, ProviderState]) -> None:
        providers = {provider_id: _state_to_dict(state) for provider_id, state in provider_states.items()}
        self.health_path.write_text(yaml.safe_dump({"providers": providers}, sort_keys=True), encoding="utf-8")

    def append_routing_decision(self, request_text: str, decision: RoutingDecision) -> None:
        history = self._read_yaml(self.history_path).get("runs", [])
        timestamp = datetime.now(tz=UTC).isoformat()
        history.append(
            {
                "timestamp": timestamp,
                "prompt_preview": request_text[:120],
                "routing_mode": decision.routing_mode.value,
                "selected_provider": decision.selected_provider,
                "selected_model": decision.selected_model,
                "fallback_provider": decision.fallback_provider,
                "fallback_model": decision.fallback_model,
                "tier_equivalent": decision.tier_equivalent,
                "confidence": decision.confidence,
                "estimated_cost": decision.estimated_cost,
                "routing_reason": decision.routing_reason,
            }
        )
        self.history_path.write_text(yaml.safe_dump({"runs": history[-200:]}, sort_keys=False), encoding="utf-8")
        self._update_cost_snapshot(history[-200:])

    def load_history(self) -> list[dict[str, Any]]:
        return list(self._read_yaml(self.history_path).get("runs", []))

    def load_cost_snapshot(self) -> dict[str, Any]:
        return self._read_yaml(self.cost_path)

    def _update_cost_snapshot(self, history: list[dict[str, Any]]) -> None:
        total_estimated = round(sum(float(item.get("estimated_cost", 0.0)) for item in history), 4)
        smart_runs = sum(1 for item in history if item.get("routing_mode") == RoutingMode.SMART_AUTO.value)
        tier_runs = sum(1 for item in history if item.get("routing_mode") == RoutingMode.TIER.value)
        snapshot = {
            "updated_at": datetime.now(tz=UTC).isoformat(),
            "run_count": len(history),
            "smart_auto_runs": smart_runs,
            "tier_runs": tier_runs,
            "estimated_api_spend": total_estimated,
        }
        self.cost_path.write_text(yaml.safe_dump(snapshot, sort_keys=False), encoding="utf-8")

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _state_to_dict(state: ProviderState) -> dict[str, Any]:
    data = asdict(state)
    data["provider_type"] = state.provider_type.value
    data["status"] = state.status.value
    for key in ("cooldown_until", "next_probe_at", "last_success_at", "last_failure_at"):
        value = data.get(key)
        if value is not None:
            data[key] = value.isoformat()
    return data


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
