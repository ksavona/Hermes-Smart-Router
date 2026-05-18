from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any

import yaml

from .models import ProviderHealthStatus, ProviderState, RoutingDecision, RoutingMode, ProviderType


class RouterStateStore:
    def __init__(
        self,
        root: Path,
        history_retention_days: int = 10,
        persist_full_prompts: bool = False,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_retention_days = max(1, int(history_retention_days))
        self.persist_full_prompts = bool(persist_full_prompts)
        self.db_path = self.root / "router_state.db"
        self.health_path = self.root / "provider_health.yaml"
        self.history_path = self.root / "routing_history.yaml"
        self.cost_path = self.root / "cost_snapshot.yaml"
        self._ensure_schema()
        self._migrate_legacy_yaml_once()
        with self._connect() as conn:
            self._prune_routing_runs(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_health (
                    provider_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quota_state TEXT NOT NULL,
                    estimated_remaining INTEGER,
                    cooldown_until TEXT,
                    next_probe_at TEXT,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    last_error_type TEXT,
                    failure_rate REAL NOT NULL,
                    timezone TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS routing_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prompt_preview TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    routing_mode TEXT NOT NULL,
                    selected_provider TEXT NOT NULL,
                    selected_model TEXT NOT NULL,
                    fallback_provider TEXT,
                    fallback_model TEXT,
                    tier_equivalent TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    estimated_cost REAL NOT NULL,
                    routing_reason TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cost_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    updated_at TEXT NOT NULL,
                    run_count INTEGER NOT NULL,
                    smart_auto_runs INTEGER NOT NULL,
                    tier_runs INTEGER NOT NULL,
                    estimated_api_spend REAL NOT NULL
                );
                """
            )

    def _migrate_legacy_yaml_once(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM routing_runs").fetchone()
            has_runs = int(row["c"]) > 0 if row else False
            row = conn.execute("SELECT COUNT(*) AS c FROM provider_health").fetchone()
            has_health = int(row["c"]) > 0 if row else False

            if has_runs or has_health:
                return

            raw_health = self._read_yaml(self.health_path).get("providers", {})
            for provider_id, saved in raw_health.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO provider_health (
                        provider_id, provider_name, provider_type, status, quota_state,
                        estimated_remaining, cooldown_until, next_probe_at, last_success_at,
                        last_failure_at, last_error_type, failure_rate, timezone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        provider_id,
                        saved.get("provider_name", provider_id),
                        saved.get("provider_type", ProviderType.NORMAL.value),
                        saved.get("status", ProviderHealthStatus.UNKNOWN.value),
                        saved.get("quota_state", "unknown"),
                        saved.get("estimated_remaining"),
                        saved.get("cooldown_until"),
                        saved.get("next_probe_at"),
                        saved.get("last_success_at"),
                        saved.get("last_failure_at"),
                        saved.get("last_error_type"),
                        float(saved.get("failure_rate", 0.0)),
                        saved.get("timezone", "UTC"),
                    ),
                )

            raw_runs = self._read_yaml(self.history_path).get("runs", [])
            for run in raw_runs[-200:]:
                preview = str(run.get("prompt_preview", ""))
                conn.execute(
                    """
                    INSERT INTO routing_runs (
                        timestamp, prompt_preview, prompt_text, routing_mode, selected_provider,
                        selected_model, fallback_provider, fallback_model, tier_equivalent,
                        confidence, estimated_cost, routing_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.get("timestamp", datetime.now(tz=UTC).isoformat()),
                        preview,
                        preview,
                        run.get("routing_mode", RoutingMode.TIER.value),
                        run.get("selected_provider", "none"),
                        run.get("selected_model", "none"),
                        run.get("fallback_provider"),
                        run.get("fallback_model"),
                        run.get("tier_equivalent", "T3"),
                        int(run.get("confidence", 0)),
                        float(run.get("estimated_cost", 0.0)),
                        run.get("routing_reason", ""),
                    ),
                )

            if raw_runs:
                self._update_cost_snapshot(conn)

    def load_provider_states(self, providers: list[dict[str, Any]]) -> dict[str, ProviderState]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM provider_health").fetchall()

        persisted = {_row_to_state(row).provider_id: _row_to_state(row) for row in rows}
        if not providers:
            return persisted

        states: dict[str, ProviderState] = {}
        for provider in providers:
            provider_id = provider["id"]
            if provider_id in persisted:
                states[provider_id] = persisted[provider_id]
                continue

            fallback = provider.get("type") == ProviderType.FALLBACK.value and provider.get("standby_only", False)
            states[provider_id] = ProviderState(
                provider_id=provider_id,
                provider_name=provider.get("name", provider_id),
                provider_type=ProviderType(provider.get("type", ProviderType.NORMAL.value)),
                status=ProviderHealthStatus.STANDBY if fallback else ProviderHealthStatus.AVAILABLE,
                quota_state="unknown",
                estimated_remaining=None,
                cooldown_until=None,
                next_probe_at=None,
                last_success_at=None,
                last_failure_at=None,
                last_error_type=None,
                failure_rate=0.0,
                timezone="UTC",
            )
        return states

    def save_provider_states(self, provider_states: dict[str, ProviderState]) -> None:
        with self._connect() as conn:
            for provider_id, state in provider_states.items():
                data = _state_to_dict(state)
                conn.execute(
                    """
                    INSERT INTO provider_health (
                        provider_id, provider_name, provider_type, status, quota_state,
                        estimated_remaining, cooldown_until, next_probe_at, last_success_at,
                        last_failure_at, last_error_type, failure_rate, timezone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider_id) DO UPDATE SET
                        provider_name=excluded.provider_name,
                        provider_type=excluded.provider_type,
                        status=excluded.status,
                        quota_state=excluded.quota_state,
                        estimated_remaining=excluded.estimated_remaining,
                        cooldown_until=excluded.cooldown_until,
                        next_probe_at=excluded.next_probe_at,
                        last_success_at=excluded.last_success_at,
                        last_failure_at=excluded.last_failure_at,
                        last_error_type=excluded.last_error_type,
                        failure_rate=excluded.failure_rate,
                        timezone=excluded.timezone
                    """,
                    (
                        provider_id,
                        data.get("provider_name", provider_id),
                        data.get("provider_type", ProviderType.NORMAL.value),
                        data.get("status", ProviderHealthStatus.UNKNOWN.value),
                        data.get("quota_state", "unknown"),
                        data.get("estimated_remaining"),
                        data.get("cooldown_until"),
                        data.get("next_probe_at"),
                        data.get("last_success_at"),
                        data.get("last_failure_at"),
                        data.get("last_error_type"),
                        float(data.get("failure_rate", 0.0)),
                        data.get("timezone", "UTC"),
                    ),
                )

    def append_routing_decision(self, request_text: str, decision: RoutingDecision) -> None:
        timestamp = datetime.now(tz=UTC).isoformat()
        prompt_preview = request_text[:120]
        prompt_text = request_text if self.persist_full_prompts else ""
        with self._connect() as conn:
            # Prevent near-duplicate inserts for the same prompt in quick succession.
            last_row = conn.execute(
                """
                SELECT timestamp, prompt_preview
                FROM routing_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if last_row and str(last_row["prompt_preview"]) == prompt_preview:
                last_ts = _parse_dt(last_row["timestamp"])
                now_ts = datetime.fromisoformat(timestamp)
                if last_ts and (now_ts - last_ts).total_seconds() < 3:
                    return

            conn.execute(
                """
                INSERT INTO routing_runs (
                    timestamp, prompt_preview, prompt_text, routing_mode, selected_provider,
                    selected_model, fallback_provider, fallback_model, tier_equivalent,
                    confidence, estimated_cost, routing_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    prompt_preview,
                    prompt_text,
                    decision.routing_mode.value,
                    decision.selected_provider,
                    decision.selected_model,
                    decision.fallback_provider,
                    decision.fallback_model,
                    decision.tier_equivalent,
                    int(decision.confidence),
                    float(decision.estimated_cost),
                    decision.routing_reason,
                ),
            )
            conn.execute(
                """
                DELETE FROM routing_runs
                WHERE id NOT IN (
                    SELECT id FROM routing_runs ORDER BY id DESC LIMIT 200
                )
                """
            )
            self._prune_routing_runs(conn)
            self._update_cost_snapshot(conn)

    def load_history(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    prompt_preview,
                    prompt_text,
                    routing_mode,
                    selected_provider,
                    selected_model,
                    fallback_provider,
                    fallback_model,
                    tier_equivalent,
                    confidence,
                    estimated_cost,
                    routing_reason
                FROM routing_runs
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def load_cost_snapshot(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT updated_at, run_count, smart_auto_runs, tier_runs, estimated_api_spend
                FROM cost_snapshot
                WHERE id = 1
                """
            ).fetchone()
        return dict(row) if row else {}

    def _update_cost_snapshot(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS run_count,
                SUM(CASE WHEN routing_mode = ? THEN 1 ELSE 0 END) AS smart_auto_runs,
                SUM(CASE WHEN routing_mode = ? THEN 1 ELSE 0 END) AS tier_runs,
                COALESCE(SUM(estimated_cost), 0.0) AS estimated_api_spend
            FROM routing_runs
            """,
            (RoutingMode.SMART_AUTO.value, RoutingMode.TIER.value),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO cost_snapshot (id, updated_at, run_count, smart_auto_runs, tier_runs, estimated_api_spend)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=excluded.updated_at,
                run_count=excluded.run_count,
                smart_auto_runs=excluded.smart_auto_runs,
                tier_runs=excluded.tier_runs,
                estimated_api_spend=excluded.estimated_api_spend
            """,
            (
                datetime.now(tz=UTC).isoformat(),
                int(row["run_count"] if row and row["run_count"] is not None else 0),
                int(row["smart_auto_runs"] if row and row["smart_auto_runs"] is not None else 0),
                int(row["tier_runs"] if row and row["tier_runs"] is not None else 0),
                round(float(row["estimated_api_spend"] if row else 0.0), 4),
            ),
        )

    def _prune_routing_runs(self, conn: sqlite3.Connection) -> None:
        # Retention policy applies to routing run data only (not learning-memory data).
        cutoff = datetime.now(tz=UTC).timestamp() - (self.history_retention_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()
        conn.execute("DELETE FROM routing_runs WHERE timestamp < ?", (cutoff_iso,))

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


def _row_to_state(row: sqlite3.Row) -> ProviderState:
    return ProviderState(
        provider_id=str(row["provider_id"]),
        provider_name=str(row["provider_name"]),
        provider_type=ProviderType(str(row["provider_type"])),
        status=ProviderHealthStatus(str(row["status"])),
        quota_state=str(row["quota_state"]),
        estimated_remaining=row["estimated_remaining"],
        cooldown_until=_parse_dt(row["cooldown_until"]),
        next_probe_at=_parse_dt(row["next_probe_at"]),
        last_success_at=_parse_dt(row["last_success_at"]),
        last_failure_at=_parse_dt(row["last_failure_at"]),
        last_error_type=row["last_error_type"],
        failure_rate=float(row["failure_rate"]),
        timezone=str(row["timezone"]),
    )
