from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re

from .models import ErrorCategory, ProviderHealthStatus, ProviderState


@dataclass(slots=True)
class InterpretationResult:
    category: ErrorCategory
    confidence: int
    retry_after: datetime | None
    human_summary: str


_PATTERNS: list[tuple[re.Pattern[str], ErrorCategory, int]] = [
    (re.compile(r"premium request limit|weekly limit|quota exceeded", re.I), ErrorCategory.SUBSCRIPTION_LIMIT, 95),
    (re.compile(r"rate limit|too many requests|try again later", re.I), ErrorCategory.RATE_LIMIT, 92),
    (re.compile(r"authentication required|invalid token|unauthorized|oauth", re.I), ErrorCategory.AUTH_FAILURE, 93),
    (re.compile(r"model unavailable|model not found", re.I), ErrorCategory.MODEL_UNAVAILABLE, 90),
    (re.compile(r"timeout|network|connection reset|dns", re.I), ErrorCategory.NETWORK_FAILURE, 85),
    (re.compile(r"service unavailable|outage|internal error", re.I), ErrorCategory.PROVIDER_OUTAGE, 80),
    (re.compile(r"invalid request|bad request", re.I), ErrorCategory.INVALID_REQUEST, 88),
]


def interpret_provider_message(message: str, now: datetime | None = None) -> InterpretationResult:
    now = now or datetime.now(tz=UTC)
    lowered = message.strip()

    for pattern, category, confidence in _PATTERNS:
        if pattern.search(lowered):
            return InterpretationResult(
                category=category,
                confidence=confidence,
                retry_after=_guess_retry_after(category, now),
                human_summary=f"Detected {category.value} from provider message.",
            )

    return InterpretationResult(
        category=ErrorCategory.UNKNOWN,
        confidence=40,
        retry_after=now + timedelta(hours=1),
        human_summary="Could not confidently classify provider message.",
    )


def apply_error_to_provider_state(
    provider_state: ProviderState,
    interpretation: InterpretationResult,
    now: datetime | None = None,
) -> ProviderState:
    now = now or datetime.now(tz=UTC)
    provider_state.last_failure_at = now
    provider_state.last_error_type = interpretation.category.value

    if interpretation.category == ErrorCategory.SUBSCRIPTION_LIMIT:
        provider_state.status = ProviderHealthStatus.SUBSCRIPTION_LIMIT
        provider_state.cooldown_until = interpretation.retry_after
        provider_state.next_probe_at = interpretation.retry_after
    elif interpretation.category == ErrorCategory.RATE_LIMIT:
        provider_state.status = ProviderHealthStatus.RATE_LIMITED
        provider_state.cooldown_until = now + timedelta(minutes=15)
        provider_state.next_probe_at = now + timedelta(minutes=30)
    elif interpretation.category == ErrorCategory.AUTH_FAILURE:
        provider_state.status = ProviderHealthStatus.AUTH_REQUIRED
        provider_state.cooldown_until = None
        provider_state.next_probe_at = None
    elif interpretation.category in {ErrorCategory.TEMPORARY_FAILURE, ErrorCategory.NETWORK_FAILURE, ErrorCategory.PROVIDER_OUTAGE}:
        provider_state.status = ProviderHealthStatus.COOLDOWN
        provider_state.cooldown_until = now + timedelta(hours=1)
        provider_state.next_probe_at = now + timedelta(hours=1)
    elif interpretation.category == ErrorCategory.MODEL_UNAVAILABLE:
        provider_state.status = ProviderHealthStatus.LIMITED
    else:
        provider_state.status = ProviderHealthStatus.UNKNOWN
        provider_state.next_probe_at = now + timedelta(hours=1)

    return provider_state


def mark_provider_available(provider_state: ProviderState, now: datetime | None = None) -> ProviderState:
    now = now or datetime.now(tz=UTC)
    provider_state.status = ProviderHealthStatus.AVAILABLE
    provider_state.cooldown_until = None
    provider_state.next_probe_at = None
    provider_state.last_success_at = now
    provider_state.last_error_type = None
    return provider_state


def _guess_retry_after(category: ErrorCategory, now: datetime) -> datetime | None:
    if category == ErrorCategory.SUBSCRIPTION_LIMIT:
        return now + timedelta(hours=6)
    if category == ErrorCategory.RATE_LIMIT:
        return now + timedelta(minutes=30)
    if category in {ErrorCategory.NETWORK_FAILURE, ErrorCategory.PROVIDER_OUTAGE}:
        return now + timedelta(hours=1)
    return None
