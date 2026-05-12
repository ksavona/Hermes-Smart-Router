from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import yaml

from .models import ProviderModel, ProviderType, RoutingMode, TierDefinition


@dataclass(slots=True)
class RouterSettings:
    routing_mode: RoutingMode = RoutingMode.SMART_AUTO
    auto_fallback_to_tier: bool = True
    timezone: str = "UTC"
    confidence_threshold: int = 75
    allow_api_fallback: bool = True
    require_confirmation_for_paid_api: bool = True
    max_api_spend_per_run: float = 0.50
    daily_api_spend_warning: float = 5.00
    weekly_api_spend_warning: float = 20.00
    provider_preservation_enabled: bool = True
    learning_memory_enabled: bool = True
    cost_tracking_enabled: bool = True
    probe_enabled: bool = True


@dataclass(slots=True)
class ProviderConfig:
    id: str
    name: str
    type: ProviderType
    auth_type: str
    enabled: bool = True
    preserve_for_unique_models: bool = False
    standby_only: bool = False


@dataclass(slots=True)
class UserPreferences:
    prefer_local_first: bool = True
    prefer_cheapest_competent: bool = True
    require_prompt_before_paid_api: bool = True
    hide_fallback_providers: bool = True
    pin_tier_models: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True)
class RouterConfig:
    settings: RouterSettings = field(default_factory=RouterSettings)
    providers: list[ProviderConfig] = field(default_factory=list)
    preferences: UserPreferences = field(default_factory=UserPreferences)
    tiers: list[TierDefinition] = field(default_factory=list)


def default_tiers() -> list[TierDefinition]:
    return [
        TierDefinition(
            tier="T1",
            name="Cheap Simple",
            purpose="Small questions, formatting, basic transforms",
            primary=ProviderModel("ollama", "qwen-local", ProviderType.NORMAL, 1, 0.0, 300, "cheap"),
            fallback=ProviderModel("gemini", "flash", ProviderType.NORMAL, 2, 0.0, 500, "cheap"),
            allow_api_fallback=False,
        ),
        TierDefinition(
            tier="T2",
            name="Fast General",
            purpose="Summaries and short analysis",
            primary=ProviderModel("gemini", "flash", ProviderType.NORMAL, 1, 0.0, 500, "general"),
            fallback=ProviderModel("codex", "gpt-5-mini", ProviderType.NORMAL, 2, 0.0, 650, "general"),
            allow_api_fallback=False,
        ),
        TierDefinition(
            tier="T3",
            name="Balanced",
            purpose="Normal coding and planning",
            primary=ProviderModel("codex", "gpt-5.4", ProviderType.NORMAL, 1, 0.0, 900, "balanced"),
            fallback=ProviderModel("copilot", "gpt-5.4", ProviderType.NORMAL, 2, 0.0, 900, "balanced"),
            allow_api_fallback=False,
        ),
        TierDefinition(
            tier="T4",
            name="Strong",
            purpose="Complex coding and multi-step reasoning",
            primary=ProviderModel("copilot", "claude-sonnet", ProviderType.NORMAL, 1, 0.0, 1200, "strong"),
            fallback=ProviderModel("codex", "gpt-5.4", ProviderType.NORMAL, 2, 0.0, 1000, "strong"),
            allow_api_fallback=True,
        ),
        TierDefinition(
            tier="T5",
            name="Premium",
            purpose="Critical and high-risk outputs",
            primary=ProviderModel("codex", "gpt-5.4", ProviderType.NORMAL, 1, 0.0, 1100, "premium"),
            fallback=ProviderModel("copilot", "gpt-5.4", ProviderType.NORMAL, 2, 0.0, 1100, "premium"),
            secondary_fallback=ProviderModel(
                "openai_api", "gpt-5.4", ProviderType.FALLBACK, 3, 0.85, 1300, "premium"
            ),
            allow_api_fallback=True,
        ),
    ]


def default_router_config() -> RouterConfig:
    providers = [
        ProviderConfig("codex", "ChatGPT Codex", ProviderType.NORMAL, "oauth", True, False, False),
        ProviderConfig("copilot", "GitHub Copilot", ProviderType.NORMAL, "oauth", True, True, False),
        ProviderConfig("gemini", "Gemini OAuth", ProviderType.NORMAL, "oauth", True, False, False),
        ProviderConfig("ollama", "Ollama Local", ProviderType.NORMAL, "local", True, False, False),
        ProviderConfig("deepseek_api", "DeepSeek API", ProviderType.FALLBACK, "api_key", True, False, True),
        ProviderConfig("openai_api", "OpenAI API", ProviderType.FALLBACK, "api_key", True, False, True),
    ]
    return RouterConfig(providers=providers, tiers=default_tiers())


def write_default_config(config_path: Path) -> RouterConfig:
    cfg = default_router_config()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(_to_serializable(cfg), sort_keys=False), encoding="utf-8")
    return cfg


def load_router_config(config_path: Path) -> RouterConfig:
    if not config_path.exists():
        return write_default_config(config_path)

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return _from_dict(raw)


def _to_serializable(cfg: RouterConfig) -> dict:
    return _coerce_enums(asdict(cfg))


def _coerce_enums(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _coerce_enums(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_enums(v) for v in value]
    return value


def _from_dict(raw: dict) -> RouterConfig:
    settings_raw = raw.get("settings", {})
    settings = RouterSettings(
        routing_mode=RoutingMode(settings_raw.get("routing_mode", RoutingMode.SMART_AUTO.value)),
        auto_fallback_to_tier=bool(settings_raw.get("auto_fallback_to_tier", True)),
        timezone=settings_raw.get("timezone", "UTC"),
        confidence_threshold=int(settings_raw.get("confidence_threshold", 75)),
        allow_api_fallback=bool(settings_raw.get("allow_api_fallback", True)),
        require_confirmation_for_paid_api=bool(settings_raw.get("require_confirmation_for_paid_api", True)),
        max_api_spend_per_run=float(settings_raw.get("max_api_spend_per_run", 0.50)),
        daily_api_spend_warning=float(settings_raw.get("daily_api_spend_warning", 5.0)),
        weekly_api_spend_warning=float(settings_raw.get("weekly_api_spend_warning", 20.0)),
        provider_preservation_enabled=bool(settings_raw.get("provider_preservation_enabled", True)),
        learning_memory_enabled=bool(settings_raw.get("learning_memory_enabled", True)),
        cost_tracking_enabled=bool(settings_raw.get("cost_tracking_enabled", True)),
        probe_enabled=bool(settings_raw.get("probe_enabled", True)),
    )

    providers = [
        ProviderConfig(
            id=p["id"],
            name=p.get("name", p["id"]),
            type=ProviderType(p.get("type", ProviderType.NORMAL.value)),
            auth_type=p.get("auth_type", "unknown"),
            enabled=bool(p.get("enabled", True)),
            preserve_for_unique_models=bool(p.get("preserve_for_unique_models", False)),
            standby_only=bool(p.get("standby_only", False)),
        )
        for p in raw.get("providers", [])
    ]

    preferences_raw = raw.get("preferences", {})
    preferences = UserPreferences(
        prefer_local_first=bool(preferences_raw.get("prefer_local_first", True)),
        prefer_cheapest_competent=bool(preferences_raw.get("prefer_cheapest_competent", True)),
        require_prompt_before_paid_api=bool(preferences_raw.get("require_prompt_before_paid_api", True)),
        hide_fallback_providers=bool(preferences_raw.get("hide_fallback_providers", True)),
        pin_tier_models=dict(preferences_raw.get("pin_tier_models", {})),
    )

    tiers: list[TierDefinition] = []
    for t in raw.get("tiers", []):
        secondary = t.get("secondary_fallback")
        tiers.append(
            TierDefinition(
                tier=t["tier"],
                name=t.get("name", t["tier"]),
                purpose=t.get("purpose", ""),
                primary=_model_from_dict(t["primary"]),
                fallback=_model_from_dict(t["fallback"]),
                secondary_fallback=_model_from_dict(secondary) if secondary else None,
                allow_escalation=bool(t.get("allow_escalation", True)),
                allow_api_fallback=bool(t.get("allow_api_fallback", False)),
            )
        )

    if not tiers:
        tiers = default_tiers()

    return RouterConfig(settings=settings, providers=providers, preferences=preferences, tiers=tiers)


def _model_from_dict(data: dict) -> ProviderModel:
    return ProviderModel(
        provider=data["provider"],
        model=data["model"],
        provider_type=ProviderType(data.get("provider_type", ProviderType.NORMAL.value)),
        priority=int(data.get("priority", 10)),
        estimated_cost_per_1k=float(data.get("estimated_cost_per_1k", 0.0)),
        latency_ms_estimate=int(data.get("latency_ms_estimate", 0)),
        capability_class=data.get("capability_class", "general"),
        model_family=data.get("model_family", "unknown"),
    )
