from pathlib import Path

from hermes_plugin_starter.models import ProviderHealthStatus, ProviderState, ProviderType, RoutingDecision, RoutingMode
from hermes_plugin_starter.state import RouterStateStore


def test_state_store_round_trips_provider_health(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path)
    provider_states = {
        "codex": ProviderState(
            provider_id="codex",
            provider_name="Codex",
            provider_type=ProviderType.NORMAL,
            status=ProviderHealthStatus.AVAILABLE,
        )
    }
    store.save_provider_states(provider_states)
    reloaded = store.load_provider_states([
        {"id": "codex", "name": "Codex", "type": "normal", "standby_only": False}
    ])
    assert reloaded["codex"].status == ProviderHealthStatus.AVAILABLE


def test_state_store_tracks_history_and_costs(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path)
    store.append_routing_decision(
        "debug this function",
        RoutingDecision(
            selected_provider="codex",
            selected_model="gpt-5.4",
            routing_reason="selected",
            confidence=90,
            tier_equivalent="T4",
            routing_mode=RoutingMode.SMART_AUTO,
            estimated_cost=0.25,
        ),
    )
    history = store.load_history()
    snapshot = store.load_cost_snapshot()
    assert len(history) == 1
    assert snapshot["smart_auto_runs"] == 1
    assert snapshot["estimated_api_spend"] == 0.25
