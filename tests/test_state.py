from pathlib import Path
from datetime import UTC, datetime, timedelta
import sqlite3

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
    assert (tmp_path / "router_state.db").exists()


def test_state_store_tracks_history_and_costs(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path)
    prompt = "debug this function"
    store.append_routing_decision(
        prompt,
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
    assert history[0]["prompt_text"] == ""
    assert history[0]["prompt_preview"] == prompt
    assert snapshot["smart_auto_runs"] == 1
    assert snapshot["estimated_api_spend"] == 0.25


def test_state_store_persists_full_prompt_when_debug_enabled(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path, persist_full_prompts=True)
    prompt = "show full prompt for debugging"
    store.append_routing_decision(
        prompt,
        RoutingDecision(
            selected_provider="codex",
            selected_model="gpt-5.4",
            routing_reason="selected",
            confidence=90,
            tier_equivalent="T4",
            routing_mode=RoutingMode.SMART_AUTO,
            estimated_cost=0.10,
        ),
    )
    history = store.load_history()
    assert history[0]["prompt_text"] == prompt


def test_state_store_prunes_history_older_than_retention(tmp_path: Path) -> None:
    store = RouterStateStore(tmp_path, history_retention_days=10)
    db_path = tmp_path / "router_state.db"
    old_ts = (datetime.now(tz=UTC) - timedelta(days=11)).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO routing_runs (
                timestamp, prompt_preview, prompt_text, routing_mode, selected_provider,
                selected_model, fallback_provider, fallback_model, tier_equivalent,
                confidence, estimated_cost, routing_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                old_ts,
                "old prompt",
                "",
                RoutingMode.TIER.value,
                "codex",
                "gpt-5.4",
                None,
                None,
                "T3",
                50,
                0.0,
                "old run",
            ),
        )

    store.append_routing_decision(
        "new prompt",
        RoutingDecision(
            selected_provider="codex",
            selected_model="gpt-5.4",
            routing_reason="new run",
            confidence=90,
            tier_equivalent="T4",
            routing_mode=RoutingMode.SMART_AUTO,
            estimated_cost=0.20,
        ),
    )

    history = store.load_history()
    assert len(history) == 1
    assert history[0]["prompt_preview"] == "new prompt"
