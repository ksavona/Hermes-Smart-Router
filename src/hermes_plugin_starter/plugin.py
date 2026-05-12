from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_router_config, write_default_config
from .models import ProviderHealthStatus, ProviderState, RoutingDecision, RoutingRequest
from .routing import route_with_tiers


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str


@dataclass(slots=True)
class HermesSmartRouterPlugin:
    config_path: Path

    def route(self, prompt: str, context: dict[str, Any] | None = None) -> RoutingDecision:
        _ = context or {}
        cfg = load_router_config(self.config_path)
        request = RoutingRequest(prompt=prompt)

        provider_states: dict[str, ProviderState] = {}
        for provider in cfg.providers:
            provider_states[provider.id] = ProviderState(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_type=provider.type,
                status=(
                    ProviderHealthStatus.STANDBY
                    if provider.type.value == "fallback" and provider.standby_only
                    else ProviderHealthStatus.AVAILABLE
                ),
            )

        return route_with_tiers(request=request, config=cfg, provider_states=provider_states)


def create_default_plugin_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        write_default_config(config_path)


def register(context: dict[str, Any] | None = None) -> PluginInfo:
    """Register plugin with Hermes and initialize local config if needed."""
    _ = context or {}
    config_path = Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_config.yaml"
    create_default_plugin_config(config_path)
    return PluginInfo(
        name="hermes-smart-router",
        version="0.1.0",
        description="Smart model routing plugin for Hermes with tier and auto modes",
    )
