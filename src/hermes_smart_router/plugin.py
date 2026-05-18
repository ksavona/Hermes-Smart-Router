from dataclasses import dataclass
from pathlib import Path
from typing import Any
import time
from .config import load_router_config, write_default_config
from .models import RoutingDecision, RoutingMode, RoutingRequest, TaskRiskLevel
from .routing import route_smart_auto, route_with_tiers
from .state import RouterStateStore


_PROVIDER_EQUIVALENTS = {
    "openai-codex": "codex",
    "codex": "openai-codex",
    "google-gemini-cli": "gemini",
    "gemini": "google-gemini-cli",
}

_AVAILABLE_MODEL_CATALOG_CACHE: tuple[float, dict[str, set[str]]] | None = None
_AVAILABLE_MODEL_CATALOG_TTL_SECONDS = 60.0


def _provider_aliases(provider: str) -> set[str]:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return set()
    aliases = {normalized}
    alt = _PROVIDER_EQUIVALENTS.get(normalized)
    if alt:
        aliases.add(alt)
    return aliases


def _to_runtime_provider_id(provider: str | None) -> str | None:
    if provider is None:
        return None
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return None
    runtime_map = {
        "codex": "openai-codex",
        "openai codex": "openai-codex",
        "gemini": "google-gemini-cli",
        "google gemini cli": "google-gemini-cli",
    }
    return runtime_map.get(normalized, normalized)


def _normalize_decision_provider_ids(decision: RoutingDecision) -> RoutingDecision:
    decision.selected_provider = _to_runtime_provider_id(decision.selected_provider) or decision.selected_provider
    decision.fallback_provider = _to_runtime_provider_id(decision.fallback_provider)
    return decision


def _load_available_model_catalog(refresh: bool = False) -> dict[str, set[str]]:
    """Best-effort Hermes runtime catalog: provider -> available model IDs.

    Discovery is cached briefly because the Hermes model-switch APIs can be
    slow when forced on every turn.
    """
    global _AVAILABLE_MODEL_CATALOG_CACHE

    now = time.time()
    if not refresh and _AVAILABLE_MODEL_CATALOG_CACHE is not None:
        cached_at, cached_catalog = _AVAILABLE_MODEL_CATALOG_CACHE
        if (now - cached_at) < _AVAILABLE_MODEL_CATALOG_TTL_SECONDS:
            return {provider: set(models) for provider, models in cached_catalog.items()}

    try:
        from hermes_cli.model_switch import list_authenticated_providers
        from hermes_cli.models import provider_model_ids
    except Exception:
        return {}

    catalog: dict[str, set[str]] = {}
    try:
        providers = list_authenticated_providers(current_provider="", current_model="", max_models=512)
    except Exception:
        return {}

    for row in providers:
        slug = str(row.get("slug", "") or "").strip().lower()
        if not slug:
            continue

        models = {str(m).strip().lower() for m in (row.get("models") or []) if str(m).strip()}
        try:
            live = provider_model_ids(slug)
            models.update(str(m).strip().lower() for m in live if str(m).strip())
        except Exception:
            pass

        if not models:
            continue

        for alias in _provider_aliases(slug):
            catalog.setdefault(alias, set()).update(models)

    _AVAILABLE_MODEL_CATALOG_CACHE = (now, {provider: set(models) for provider, models in catalog.items()})
    return {provider: set(models) for provider, models in catalog.items()}

@dataclass
class PluginInfo:
    name: str
    version: str
    description: str

@dataclass(slots=True)
class HermesSmartRouterPlugin:
    config_path: Path
    name: str = "hermes-smart-router"
    version: str = "0.2.0"
    description: str = "Smart model routing plugin for Hermes with tier and auto modes"

    def route(self, prompt: str, context: dict[str, Any] | None = None) -> RoutingDecision:
        context = context or {}
        cfg = load_router_config(self.config_path)
        request = RoutingRequest(
            prompt=prompt,
            requires_tools=bool(context.get("requires_tools", False)),
            requires_code=bool(context.get("requires_code", False)),
            requires_reasoning=bool(context.get("requires_reasoning", False)),
            required_context_size=int(context.get("required_context_size", 0)),
            risk_level=risk_level_from_context(context),
            user_preference=context.get("user_preference"),
        )
        state_store = RouterStateStore(
            self.config_path.parent,
            history_retention_days=cfg.settings.routing_history_retention_days,
            persist_full_prompts=cfg.settings.store_full_prompts_for_debug,
        )
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
        available_catalog = _load_available_model_catalog(refresh=bool(context.get("refresh_model_catalog", False)))
        if cfg.settings.routing_mode == RoutingMode.SMART_AUTO:
            decision = route_smart_auto(
                request=request,
                config=cfg,
                provider_states=provider_states,
                available_models=available_catalog,
            )
        else:
            decision = route_with_tiers(
                request=request,
                config=cfg,
                provider_states=provider_states,
                available_models=available_catalog,
            )
        decision = _normalize_decision_provider_ids(decision)
        state_store.save_provider_states(provider_states)
        state_store.append_routing_decision(prompt, decision)
        return decision

def create_default_plugin_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        write_default_config(config_path)

def resolve_config_path(context: dict[str, Any]) -> Path:
    configured_path = context.get("config_path")
    if configured_path:
        return Path(configured_path)
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_config.yaml"

def risk_level_from_context(context: dict[str, Any]) -> TaskRiskLevel:
    raw = context.get("risk_level", TaskRiskLevel.LOW)
    if isinstance(raw, TaskRiskLevel):
        return raw
    try:
        return TaskRiskLevel(str(raw).lower())
    except ValueError:
        return TaskRiskLevel.LOW
