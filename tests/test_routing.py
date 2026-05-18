from hermes_plugin_starter.config import default_router_config
from hermes_plugin_starter.models import ProviderHealthStatus, ProviderModel, ProviderState, ProviderType, RoutingRequest, TaskRiskLevel
from hermes_plugin_starter.routing import map_request_to_tier, route_smart_auto, route_with_tiers


def test_critical_requests_map_to_t5() -> None:
    req = RoutingRequest(prompt="Need legal risk analysis", risk_level=TaskRiskLevel.CRITICAL)
    assert map_request_to_tier(req) == "T5"


def test_tier_routing_uses_available_primary() -> None:
    cfg = default_router_config()
    provider_states = {
        "codex": ProviderState("codex", "Codex", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "copilot": ProviderState("copilot", "Copilot", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "gemini": ProviderState("gemini", "Gemini", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "ollama": ProviderState("ollama", "Ollama", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "deepseek_api": ProviderState("deepseek_api", "DeepSeek", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
        "openai_api": ProviderState("openai_api", "OpenAI", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
    }
    decision = route_with_tiers(RoutingRequest(prompt="Write a short summary"), cfg, provider_states)
    assert decision.selected_provider in {"codex", "copilot"}
    assert decision.routing_mode.value == "tier"


def test_smart_auto_preserves_more_flexible_provider_when_capability_is_equal() -> None:
    cfg = default_router_config()
    provider_states = {
        "codex": ProviderState("codex", "Codex", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "copilot": ProviderState("copilot", "Copilot", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "gemini": ProviderState("gemini", "Gemini", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "ollama": ProviderState("ollama", "Ollama", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "deepseek_api": ProviderState("deepseek_api", "DeepSeek", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
        "openai_api": ProviderState("openai_api", "OpenAI", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
    }
    request = RoutingRequest(
        prompt="Use a GPT-class model to debug this Python function",
        requires_code=True,
        requires_reasoning=True,
        user_preference="gpt",
    )
    decision = route_smart_auto(request, cfg, provider_states)
    assert decision.selected_provider == "codex"
    assert decision.routing_mode.value == "smart_auto"


def test_smart_auto_falls_back_to_tier_when_threshold_is_too_high() -> None:
    cfg = default_router_config()
    cfg.settings.confidence_threshold = 99
    provider_states = {
        "codex": ProviderState("codex", "Codex", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "copilot": ProviderState("copilot", "Copilot", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "gemini": ProviderState("gemini", "Gemini", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "ollama": ProviderState("ollama", "Ollama", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "deepseek_api": ProviderState("deepseek_api", "DeepSeek", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
        "openai_api": ProviderState("openai_api", "OpenAI", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
    }
    request = RoutingRequest(prompt="Debug this Python function", requires_code=True, requires_reasoning=True)
    decision = route_smart_auto(request, cfg, provider_states)
    assert decision.routing_mode.value == "smart_auto"
    assert "below threshold" in decision.routing_reason


def test_smart_auto_falls_back_to_tier_on_large_divergence() -> None:
    cfg = default_router_config()
    cfg.settings.smart_tier_recheck_on_divergence = False
    cfg.settings.smart_tier_price_ratio_guard = 2.0
    cfg.settings.smart_tier_capability_delta_guard = 1
    cfg.tiers[2].primary = ProviderModel(
        provider="copilot",
        model="gpt-5-mini",
        provider_type=ProviderType.NORMAL,
        priority=1,
        estimated_cost_per_1k=0.00025,
        latency_ms_estimate=200,
        capability_class="cheap",
        model_family="gpt",
    )
    cfg.tiers[2].fallback = ProviderModel(
        provider="codex",
        model="gpt-5.4-mini",
        provider_type=ProviderType.NORMAL,
        priority=2,
        estimated_cost_per_1k=0.00075,
        latency_ms_estimate=220,
        capability_class="cheap",
        model_family="gpt",
    )
    cfg.tiers[2].additional_candidates = [
        ProviderModel(
            provider="codex",
            model="gpt-5.5",
            provider_type=ProviderType.NORMAL,
            priority=10,
            estimated_cost_per_1k=0.005,
            latency_ms_estimate=500,
            capability_class="premium",
            model_family="gpt",
        )
    ]

    provider_states = {
        "codex": ProviderState("codex", "Codex", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "copilot": ProviderState("copilot", "Copilot", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "gemini": ProviderState("gemini", "Gemini", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "ollama": ProviderState("ollama", "Ollama", ProviderType.NORMAL, ProviderHealthStatus.AVAILABLE),
        "deepseek_api": ProviderState("deepseek_api", "DeepSeek", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
        "openai_api": ProviderState("openai_api", "OpenAI", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
    }

    request = RoutingRequest(prompt="debug this module", requires_code=True)
    decision = route_smart_auto(request, cfg, provider_states)
    assert decision.routing_mode.value == "tier"
    assert "diverged strongly" in decision.routing_reason


def test_smart_auto_marks_api_fallback_when_fallback_provider_selected() -> None:
    cfg = default_router_config()
    cfg.settings.confidence_threshold = 0
    cfg.tiers[-1].primary = ProviderModel(
        provider="openai_api",
        model="gpt-5.5",
        provider_type=ProviderType.FALLBACK,
        priority=1,
        estimated_cost_per_1k=0.005,
        latency_ms_estimate=500,
        capability_class="premium",
        model_family="gpt",
    )
    provider_states = {
        "codex": ProviderState("codex", "Codex", ProviderType.NORMAL, ProviderHealthStatus.UNAVAILABLE),
        "copilot": ProviderState("copilot", "Copilot", ProviderType.NORMAL, ProviderHealthStatus.UNAVAILABLE),
        "gemini": ProviderState("gemini", "Gemini", ProviderType.NORMAL, ProviderHealthStatus.UNAVAILABLE),
        "ollama": ProviderState("ollama", "Ollama", ProviderType.NORMAL, ProviderHealthStatus.UNAVAILABLE),
        "deepseek_api": ProviderState("deepseek_api", "DeepSeek", ProviderType.FALLBACK, ProviderHealthStatus.STANDBY),
        "openai_api": ProviderState("openai_api", "OpenAI", ProviderType.FALLBACK, ProviderHealthStatus.AVAILABLE),
    }
    request = RoutingRequest(prompt="Need critical incident response", requires_reasoning=True, risk_level=TaskRiskLevel.CRITICAL)
    decision = route_smart_auto(request, cfg, provider_states)
    assert decision.selected_provider == "openai_api"
    assert decision.allow_api_fallback is True
