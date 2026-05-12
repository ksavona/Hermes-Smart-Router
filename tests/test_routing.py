from hermes_plugin_starter.config import default_router_config
from hermes_plugin_starter.models import ProviderHealthStatus, ProviderState, ProviderType, RoutingRequest, TaskRiskLevel
from hermes_plugin_starter.routing import map_request_to_tier, route_with_tiers


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
