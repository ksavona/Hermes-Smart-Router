from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RoutingMode(str, Enum):
    TIER = "tier"
    SMART_AUTO = "smart_auto"


class ProviderType(str, Enum):
    NORMAL = "normal"
    FALLBACK = "fallback"


class ProviderHealthStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    RATE_LIMITED = "RATE_LIMITED"
    SUBSCRIPTION_LIMIT = "SUBSCRIPTION_LIMIT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    COOLDOWN = "COOLDOWN"
    PROBING = "PROBING"
    UNKNOWN = "UNKNOWN"
    STANDBY = "STANDBY"


class ErrorCategory(str, Enum):
    SUBSCRIPTION_LIMIT = "SUBSCRIPTION_LIMIT"
    RATE_LIMIT = "RATE_LIMIT"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    AUTH_FAILURE = "AUTH_FAILURE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN = "UNKNOWN"


class TaskRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class ProviderModel:
    provider: str
    model: str
    provider_type: ProviderType = ProviderType.NORMAL
    priority: int = 10
    estimated_cost_per_1k: float = 0.0
    latency_ms_estimate: int = 0
    capability_class: str = "general"
    model_family: str = "unknown"


@dataclass(slots=True)
class ProviderState:
    provider_id: str
    provider_name: str
    provider_type: ProviderType
    status: ProviderHealthStatus = ProviderHealthStatus.UNKNOWN
    quota_state: str = "unknown"
    estimated_remaining: int | None = None
    cooldown_until: datetime | None = None
    next_probe_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_type: str | None = None
    failure_rate: float = 0.0
    timezone: str = "UTC"


@dataclass(slots=True)
class TierDefinition:
    tier: str
    name: str
    purpose: str
    primary: ProviderModel
    fallback: ProviderModel
    secondary_fallback: ProviderModel | None = None
    additional_candidates: list[ProviderModel] = field(default_factory=list)
    allow_escalation: bool = True
    allow_api_fallback: bool = False


@dataclass(slots=True)
class RoutingRequest:
    prompt: str
    requires_tools: bool = False
    requires_code: bool = False
    requires_reasoning: bool = False
    required_context_size: int = 0
    risk_level: TaskRiskLevel = TaskRiskLevel.LOW
    user_preference: str | None = None


@dataclass(slots=True)
class RoutingDecision:
    selected_provider: str
    selected_model: str
    fallback_provider: str | None = None
    fallback_model: str | None = None
    routing_reason: str = ""
    confidence: int = 0
    tier_equivalent: str = "T3"
    allow_api_fallback: bool = False
    routing_mode: RoutingMode = RoutingMode.TIER
    estimated_cost: float = 0.0


@dataclass(slots=True)
class RuntimeEvent:
    level: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
