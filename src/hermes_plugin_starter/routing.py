from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import RouterConfig
from .models import (
    ProviderHealthStatus,
    ProviderModel,
    ProviderState,
    RoutingDecision,
    RoutingMode,
    RoutingRequest,
    TaskRiskLevel,
    TierDefinition,
)


@dataclass(slots=True)
class CandidateScore:
    provider: str
    model: str
    score: float
    estimated_cost: float


def map_request_to_tier(request: RoutingRequest) -> str:
    prompt_len = len(request.prompt)

    if request.risk_level == TaskRiskLevel.CRITICAL:
        return "T5"
    if request.requires_reasoning and request.requires_code:
        return "T4"
    if prompt_len > 6000 or request.required_context_size > 50000:
        return "T4"
    if request.requires_code or request.requires_reasoning:
        return "T3"
    if prompt_len > 1000:
        return "T2"
    return "T1"


def route_with_tiers(
    request: RoutingRequest,
    config: RouterConfig,
    provider_states: dict[str, ProviderState],
) -> RoutingDecision:
    tier_key = map_request_to_tier(request)
    tier = _get_tier(config.tiers, tier_key)

    selected = _first_available([tier.primary, tier.fallback, tier.secondary_fallback], provider_states, tier)
    if selected is None:
        if tier.allow_escalation:
            selected, tier_key = _escalate_tier(tier_key, config.tiers, provider_states)
        if selected is None:
            return RoutingDecision(
                selected_provider="none",
                selected_model="none",
                routing_reason="No eligible model is available for request.",
                confidence=0,
                tier_equivalent=tier_key,
                allow_api_fallback=False,
                routing_mode=RoutingMode.TIER,
            )

    fallback = tier.fallback if selected.provider != tier.fallback.provider else tier.primary
    return RoutingDecision(
        selected_provider=selected.provider,
        selected_model=selected.model,
        fallback_provider=fallback.provider,
        fallback_model=fallback.model,
        routing_reason="Tier routing selected the cheapest competent available model.",
        confidence=86,
        tier_equivalent=tier_key,
        allow_api_fallback=tier.allow_api_fallback,
        routing_mode=RoutingMode.TIER,
        estimated_cost=selected.estimated_cost_per_1k,
    )


def route_with_scoring(
    request: RoutingRequest,
    candidates: list[ProviderModel],
    provider_states: dict[str, ProviderState],
    flexibility_scores: dict[str, float],
) -> CandidateScore | None:
    scored: list[CandidateScore] = []

    for model in candidates:
        state = provider_states.get(model.provider)
        if not state or state.status not in {
            ProviderHealthStatus.AVAILABLE,
            ProviderHealthStatus.LIMITED,
            ProviderHealthStatus.STANDBY,
        }:
            continue

        task_fit = _task_fit_score(request, model)
        capability = _capability_score(model)
        health = 15.0 if state.status == ProviderHealthStatus.AVAILABLE else 8.0
        quota = 10.0 if state.estimated_remaining is None else min(10.0, state.estimated_remaining / 10)
        preservation = max(0.0, 10.0 - flexibility_scores.get(model.provider, 10.0))
        latency = max(0.0, 12.0 - (model.latency_ms_estimate / 250.0))
        cost_penalty = model.estimated_cost_per_1k * 10.0
        failure_risk = state.failure_rate * 10.0

        total = task_fit + capability + health + quota + preservation + latency - cost_penalty - failure_risk
        scored.append(
            CandidateScore(
                provider=model.provider,
                model=model.model,
                score=total,
                estimated_cost=model.estimated_cost_per_1k,
            )
        )

    if not scored:
        return None

    scored.sort(key=lambda item: (-item.score, item.estimated_cost, item.provider))
    return scored[0]


def _get_tier(tiers: Iterable[TierDefinition], tier_key: str) -> TierDefinition:
    for tier in tiers:
        if tier.tier == tier_key:
            return tier
    return next(iter(tiers))


def _first_available(
    models: list[ProviderModel | None],
    provider_states: dict[str, ProviderState],
    tier: TierDefinition,
) -> ProviderModel | None:
    for model in models:
        if model is None:
            continue
        state = provider_states.get(model.provider)
        if state is None:
            continue
        if state.status in {ProviderHealthStatus.AVAILABLE, ProviderHealthStatus.LIMITED}:
            return model
        if state.status == ProviderHealthStatus.STANDBY and tier.allow_api_fallback:
            return model
    return None


def _escalate_tier(
    tier_key: str,
    tiers: list[TierDefinition],
    provider_states: dict[str, ProviderState],
) -> tuple[ProviderModel | None, str]:
    tier_names = [t.tier for t in tiers]
    try:
        index = tier_names.index(tier_key)
    except ValueError:
        return None, tier_key

    for next_tier in tiers[index + 1 :]:
        model = _first_available([next_tier.primary, next_tier.fallback, next_tier.secondary_fallback], provider_states, next_tier)
        if model:
            return model, next_tier.tier
    return None, tier_key


def _task_fit_score(request: RoutingRequest, model: ProviderModel) -> float:
    capability = model.capability_class.lower()
    if request.risk_level == TaskRiskLevel.CRITICAL and capability == "premium":
        return 30.0
    if request.requires_reasoning and capability in {"premium", "strong"}:
        return 24.0
    if request.requires_code and capability in {"balanced", "strong", "premium"}:
        return 20.0
    if capability in {"cheap", "general"} and len(request.prompt) < 1000:
        return 18.0
    return 12.0


def _capability_score(model: ProviderModel) -> float:
    cap = model.capability_class.lower()
    table = {
        "cheap": 8.0,
        "general": 12.0,
        "balanced": 16.0,
        "strong": 20.0,
        "premium": 24.0,
    }
    return table.get(cap, 10.0)
