from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_router_config, write_default_config
from .models import RoutingDecision, RoutingMode, RoutingRequest
from .routing import route_smart_auto, route_with_tiers
from .state import RouterStateStore


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str


@dataclass(slots=True)
class HermesSmartRouterPlugin:
    config_path: Path

    def route(self, prompt: str, context: dict[str, Any] | None = None) -> RoutingDecision:
        context = context or {}
        cfg = load_router_config(self.config_path)
        request = RoutingRequest(
            prompt=prompt,
            requires_tools=bool(context.get("requires_tools", False)),
            requires_code=bool(context.get("requires_code", False)),
            requires_reasoning=bool(context.get("requires_reasoning", False)),
            required_context_size=int(context.get("required_context_size", 0)),
            user_preference=context.get("user_preference"),
        )

        state_store = RouterStateStore(self.config_path.parent)
        provider_states = state_store.load_provider_states([
            {
                "id": provider.id,
                "name": provider.name,
                "type": provider.type.value,
                "standby_only": provider.standby_only,
            }
            for provider in cfg.providers
            if provider.enabled
        ])

        if cfg.settings.routing_mode == RoutingMode.SMART_AUTO:
            decision = route_smart_auto(request=request, config=cfg, provider_states=provider_states)
        else:
            decision = route_with_tiers(request=request, config=cfg, provider_states=provider_states)

        state_store.save_provider_states(provider_states)
        state_store.append_routing_decision(prompt, decision)
        return decision


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
