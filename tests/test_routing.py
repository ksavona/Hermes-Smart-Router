from hermes_plugin_starter.config import default_router_config
from hermes_plugin_starter.models import ProviderHealthStatus, ProviderState, ProviderType, RoutingRequest, TaskRiskLevel
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
    assert decision.selected_provider in {"ollama", "gemini"}
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
    assert decision.routing_mode.value == "tier"
    assert "Fell back to tier routing" in decision.routing_reason
