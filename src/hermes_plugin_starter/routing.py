from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import RouterConfig
from .models import (
    ProviderHealthStatus,
    ProviderModel,
    ProviderState,
    ProviderType,
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


def route_smart_auto(
    request: RoutingRequest,
    config: RouterConfig,
    provider_states: dict[str, ProviderState],
    available_models: dict[str, set[str]] | None = None,
) -> RoutingDecision:
    candidates = collect_candidate_models(config)
    candidates = _filter_candidates_by_available_models(candidates, available_models)
    candidates = _filter_candidates_for_provider_rules(candidates, provider_states)
    flexibility_scores = provider_flexibility_scores(candidates)
    selected = route_with_scoring(request, candidates, provider_states, flexibility_scores)

    if selected is None:
        return _fallback_to_tier(
            request,
            config,
            provider_states,
            "No smart-routing candidate was available.",
            available_models,
        )

    tier_key = map_request_to_tier(request)
    tier_decision = route_with_tiers(
        request=request,
        config=config,
        provider_states=provider_states,
        available_models=available_models,
    )


    confidence = _confidence_from_score(selected.score)
    fallback = _next_best_candidate(selected, request, candidates, provider_states, flexibility_scores)

    # Gather tier candidates for reasoning output
    tier = _get_tier(config.tiers, tier_key)
    tier_candidates = _tier_candidates(tier)
    tier_models_str = "\n      ".join([
        f"{m.provider}/{m.model} (cost: €{m.estimated_cost_per_1k:.6f}, capability: {m.capability_class})"
        for m in tier_candidates
    ])

    smart_reason = (
        f"Smart auto is always primary.\n"
        f"- Smart auto selected: {selected.provider}/{selected.model} (cost: €{selected.estimated_cost:.6f}, capability: {_find_provider_model(candidates, selected.provider, selected.model).capability_class})\n"
        f"- Tier classification: {tier_key}\n"
        f"- Tier candidate models (ordered by price):\n      {tier_models_str}\n"
    )
    if confidence < config.settings.confidence_threshold:
        smart_reason += (
            f"- Smart auto confidence {confidence} is below threshold {config.settings.confidence_threshold}, but smart_auto remains primary if valid and tier-aligned.\n"
        )

    smart_reason += "- Tier is only invoked if smart_auto fails or there is a major price/capability divergence.\n"

    smart_decision = RoutingDecision(
        selected_provider=selected.provider,
        selected_model=selected.model,
        fallback_provider=fallback.provider if fallback else None,
        fallback_model=fallback.model if fallback else None,
        routing_reason=smart_reason,
        confidence=confidence,
        tier_equivalent=tier_key,
        allow_api_fallback=provider_states[selected.provider].provider_type == ProviderType.FALLBACK,
        routing_mode=RoutingMode.SMART_AUTO,
        estimated_cost=selected.estimated_cost,
    )

    if not config.settings.smart_tier_alignment_enabled:
        return smart_decision


    divergence = _smart_vs_tier_divergence(
        smart_model=_find_provider_model(candidates, selected.provider, selected.model),
        tier_model=_find_provider_model(candidates, tier_decision.selected_provider, tier_decision.selected_model),
        price_ratio_guard=max(1.0, float(config.settings.smart_tier_price_ratio_guard)),
        capability_delta_guard=max(1, int(config.settings.smart_tier_capability_delta_guard)),
    )
    if not divergence["is_vastly_different"]:
        smart_decision.routing_reason += (
            f"- Price/capability comparison: price_ratio={divergence['price_ratio']:.2f}, capability_delta={divergence['capability_delta']}.\n"
            f"- No major divergence detected. Using smart_auto selection.\n"
        )
        return smart_decision

    if config.settings.smart_tier_recheck_on_divergence:
        recheck = _recheck_with_higher_tiers(
            request=request,
            config=config,
            provider_states=provider_states,
            candidates=candidates,
            tier_key=tier_key,
        )
        if recheck and (recheck.provider, recheck.model) == (selected.provider, selected.model):
            smart_decision.routing_reason += (
                f"- Smart-vs-tier divergence detected (price_ratio={divergence['price_ratio']:.2f}, capability_delta={divergence['capability_delta']}).\n"
                f"- Higher-tier recheck confirmed smart_auto selection. Consider updating tier candidates.\n"
            )
            return smart_decision

    tier_decision.routing_reason = (
        f"Smart_auto selection diverged strongly from tier baseline (price_ratio={divergence['price_ratio']:.2f}, capability_delta={divergence['capability_delta']}).\n"
        f"- Using tier routing and flagging tier config for review.\n"
        f"- Please evaluate if the tier configuration should be updated to better match smart_auto.\n"
    )
    return tier_decision


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
    available_models: dict[str, set[str]] | None = None,
) -> RoutingDecision:
    tier_key = map_request_to_tier(request)
    tier = _get_tier(config.tiers, tier_key)
    tier_candidates = _tier_candidates(tier)

    selected = _first_available(
        tier_candidates,
        provider_states,
        tier,
        available_models,
    )
    if selected is None:
        if tier.allow_escalation:
            selected, tier_key = _escalate_tier(tier_key, config.tiers, provider_states, available_models)
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

    fallback = _next_tier_fallback(selected, tier_candidates, available_models)
    return RoutingDecision(
        selected_provider=selected.provider,
        selected_model=selected.model,
        fallback_provider=fallback.provider if fallback else None,
        fallback_model=fallback.model if fallback else None,
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
    positive_costs = [m.estimated_cost_per_1k for m in candidates if m.estimated_cost_per_1k > 0]
    cheapest_cost = min(positive_costs) if positive_costs else 0.0

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
        cost_penalty = _cost_penalty(request, model, cheapest_cost)
        overkill_penalty = _overkill_penalty(request, model)
        underfit_penalty = _underfit_penalty(request, model)
        failure_risk = state.failure_rate * 10.0

        total = (
            task_fit
            + capability
            + health
            + quota
            + preservation
            + latency
            - cost_penalty
            - failure_risk
            - overkill_penalty
            - underfit_penalty
        )
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


def collect_candidate_models(config: RouterConfig) -> list[ProviderModel]:
    seen: set[tuple[str, str]] = set()
    candidates: list[ProviderModel] = []
    for tier in config.tiers:
        for model in _tier_candidates(tier):
            if model is None:
                continue
            key = (model.provider, model.model)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(model)
    return candidates


def provider_flexibility_scores(candidates: list[ProviderModel]) -> dict[str, float]:
    families: dict[str, set[str]] = {}
    models: dict[str, set[str]] = {}

    for candidate in candidates:
        families.setdefault(candidate.provider, set()).add(candidate.model_family)
        models.setdefault(candidate.provider, set()).add(candidate.model)

    return {
        provider: min(10.0, float((len(provider_families) * 3) + len(models.get(provider, set()))))
        for provider, provider_families in families.items()
    }


def _get_tier(tiers: Iterable[TierDefinition], tier_key: str) -> TierDefinition:
    for tier in tiers:
        if tier.tier == tier_key:
            return tier
    return next(iter(tiers))


def _first_available(
    models: list[ProviderModel | None],
    provider_states: dict[str, ProviderState],
    tier: TierDefinition,
    available_models: dict[str, set[str]] | None = None,
) -> ProviderModel | None:
    for model in models:
        if model is None:
            continue
        if not _candidate_is_available(model, available_models):
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
    available_models: dict[str, set[str]] | None = None,
) -> tuple[ProviderModel | None, str]:
    tier_names = [t.tier for t in tiers]
    try:
        index = tier_names.index(tier_key)
    except ValueError:
        return None, tier_key

    for next_tier in tiers[index + 1 :]:
        model = _first_available(
            _tier_candidates(next_tier),
            provider_states,
            next_tier,
            available_models,
        )
        if model:
            return model, next_tier.tier
    return None, tier_key


def _task_fit_score(request: RoutingRequest, model: ProviderModel) -> float:
    capability = model.capability_class.lower()
    preference = (request.user_preference or "").strip().lower()

    if preference:
        if preference in {model.provider.lower(), model.model.lower(), model.model_family.lower()}:
            return 28.0
        return 6.0

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
        "fast": 8.0,
        "general": 12.0,
        "balanced": 16.0,
        "strong": 20.0,
        "premium": 24.0,
    }
    return table.get(cap, 10.0)


def _capability_rank(capability_class: str) -> int:
    table = {
        "cheap": 1,
        "fast": 1,
        "general": 2,
        "balanced": 3,
        "strong": 4,
        "premium": 5,
    }
    return table.get((capability_class or "").strip().lower(), 2)


def _required_capability_rank(request: RoutingRequest) -> int:
    tier = map_request_to_tier(request)
    table = {
        "T1": 1,
        "T2": 2,
        "T3": 3,
        "T4": 4,
        "T5": 5,
    }
    return table.get(tier, 2)


def _overkill_penalty(request: RoutingRequest, model: ProviderModel) -> float:
    required = _required_capability_rank(request)
    actual = _capability_rank(model.capability_class)
    delta = max(0, actual - required)
    if delta == 0:
        return 0.0

    # Keep simple requests from drifting to expensive, overpowered models.
    if required <= 2:
        return float(delta * 6)
    return float(delta * 2)


def _underfit_penalty(request: RoutingRequest, model: ProviderModel) -> float:
    required = _required_capability_rank(request)
    actual = _capability_rank(model.capability_class)
    delta = max(0, required - actual)
    if delta == 0:
        return 0.0

    # Heavily discourage selecting weaker models than task complexity requires.
    return float(delta * 9)


def _cost_penalty(request: RoutingRequest, model: ProviderModel, cheapest_cost: float) -> float:
    # Use relative pricing pressure against the cheapest eligible model.
    # This keeps scores stable as absolute provider prices change over time.
    simple_request = (
        len(request.prompt) < 1000
        and not request.requires_code
        and not request.requires_reasoning
        and request.risk_level != TaskRiskLevel.CRITICAL
    )
    model_cost = max(0.0, model.estimated_cost_per_1k)
    if model_cost <= 0.0 or cheapest_cost <= 0.0:
        return 0.0

    ratio = model_cost / cheapest_cost
    relative_delta = max(0.0, ratio - 1.0)

    if simple_request:
        return (relative_delta * 3.0) + (model_cost * 300.0)
    return (relative_delta * 1.2) + (model_cost * 120.0)


def _filter_candidates_for_provider_rules(
    candidates: list[ProviderModel],
    provider_states: dict[str, ProviderState],
) -> list[ProviderModel]:
    normal_by_model: dict[str, bool] = {}
    for candidate in candidates:
        state = provider_states.get(candidate.provider)
        if state and state.provider_type == candidate.provider_type and candidate.provider_type != ProviderType.FALLBACK:
            if state.status in {ProviderHealthStatus.AVAILABLE, ProviderHealthStatus.LIMITED}:
                normal_by_model[candidate.model] = True

    filtered: list[ProviderModel] = []
    for candidate in candidates:
        state = provider_states.get(candidate.provider)
        if state is None:
            continue
        if candidate.provider_type == ProviderType.FALLBACK and normal_by_model.get(candidate.model, False):
            continue
        filtered.append(candidate)
    return filtered


def _confidence_from_score(score: float) -> int:
    return max(45, min(98, int(score * 1.3)))


def _fallback_to_tier(
    request: RoutingRequest,
    config: RouterConfig,
    provider_states: dict[str, ProviderState],
    reason: str,
    available_models: dict[str, set[str]] | None = None,
) -> RoutingDecision:
    decision = route_with_tiers(request, config, provider_states, available_models)
    decision.routing_reason = f"{reason} Fell back to tier routing."
    return decision


def _filter_candidates_by_available_models(
    candidates: list[ProviderModel],
    available_models: dict[str, set[str]] | None,
) -> list[ProviderModel]:
    return [candidate for candidate in candidates if _candidate_is_available(candidate, available_models)]


def _candidate_is_available(
    candidate: ProviderModel,
    available_models: dict[str, set[str]] | None,
) -> bool:
    if not available_models:
        return True

    provider = candidate.provider.strip().lower()
    model = candidate.model.strip().lower()
    models_for_provider = available_models.get(provider)
    if not models_for_provider:
        return False
    return model in models_for_provider


def _next_best_candidate(
    selected: CandidateScore,
    request: RoutingRequest,
    candidates: list[ProviderModel],
    provider_states: dict[str, ProviderState],
    flexibility_scores: dict[str, float],
) -> CandidateScore | None:
    scored_other_provider: list[CandidateScore] = []
    scored_same_provider: list[CandidateScore] = []
    for model in candidates:
        if model.provider == selected.provider and model.model == selected.model:
            continue
        score = route_with_scoring(request, [model], provider_states, flexibility_scores)
        if score is not None:
            if score.provider != selected.provider:
                scored_other_provider.append(score)
            else:
                scored_same_provider.append(score)

    if scored_other_provider:
        scored_other_provider.sort(key=lambda item: (-item.score, item.estimated_cost, item.provider))
        return scored_other_provider[0]

    if scored_same_provider:
        scored_same_provider.sort(key=lambda item: (-item.score, item.estimated_cost, item.provider))
        return scored_same_provider[0]

    return None


def _tier_candidates(tier: TierDefinition) -> list[ProviderModel]:
    models: list[ProviderModel] = [
        tier.primary,
        tier.fallback,
        tier.secondary_fallback,
        *(tier.additional_candidates or []),
    ]
    # Keep tier pools ordered by cost first, then explicit priority as tie-breaker.
    return sorted(
        [m for m in models if m is not None],
        key=lambda m: (max(0.0, float(m.estimated_cost_per_1k)), int(m.priority), m.provider, m.model),
    )


def _next_tier_fallback(
    selected: ProviderModel,
    tier_candidates: list[ProviderModel],
    available_models: dict[str, set[str]] | None,
) -> ProviderModel | None:
    for candidate in tier_candidates:
        if candidate.provider == selected.provider and candidate.model == selected.model:
            continue
        if _candidate_is_available(candidate, available_models):
            return candidate
    return None


def _find_provider_model(candidates: list[ProviderModel], provider: str, model: str) -> ProviderModel | None:
    for candidate in candidates:
        if candidate.provider == provider and candidate.model == model:
            return candidate
    return None


def _smart_vs_tier_divergence(
    smart_model: ProviderModel | None,
    tier_model: ProviderModel | None,
    price_ratio_guard: float,
    capability_delta_guard: int,
) -> dict[str, float | int | bool]:
    if not smart_model or not tier_model:
        return {
            "price_ratio": 1.0,
            "capability_delta": 0,
            "is_vastly_different": False,
        }

    smart_cost = max(0.0, float(smart_model.estimated_cost_per_1k))
    tier_cost = max(0.0, float(tier_model.estimated_cost_per_1k))
    if smart_cost == 0.0 or tier_cost == 0.0:
        price_ratio = 1.0
    else:
        price_ratio = max(smart_cost, tier_cost) / min(smart_cost, tier_cost)

    capability_delta = abs(_capability_rank(smart_model.capability_class) - _capability_rank(tier_model.capability_class))
    is_vast = bool(price_ratio >= price_ratio_guard and capability_delta >= capability_delta_guard)
    return {
        "price_ratio": price_ratio,
        "capability_delta": capability_delta,
        "is_vastly_different": is_vast,
    }


def _recheck_with_higher_tiers(
    request: RoutingRequest,
    config: RouterConfig,
    provider_states: dict[str, ProviderState],
    candidates: list[ProviderModel],
    tier_key: str,
) -> CandidateScore | None:
    tier_names = [t.tier for t in config.tiers]
    try:
        current_index = tier_names.index(tier_key)
    except ValueError:
        return None

    # Re-check against stronger tiers to validate whether smart selection is justified.
    start_index = max(current_index + 1, 2) if len(config.tiers) >= 3 else current_index + 1
    if start_index >= len(config.tiers):
        return None

    elevated_keys = {t.tier for t in config.tiers[start_index:]}
    elevated_candidates = [
        model
        for model in candidates
        if _tier_for_model(model, config.tiers) in elevated_keys
    ]
    if not elevated_candidates:
        return None

    flexibility_scores = provider_flexibility_scores(candidates)
    return route_with_scoring(request, elevated_candidates, provider_states, flexibility_scores)


def _tier_for_model(model: ProviderModel, tiers: list[TierDefinition]) -> str | None:
    for tier in tiers:
        for candidate in _tier_candidates(tier):
            if candidate.provider == model.provider and candidate.model == model.model:
                return tier.tier
    return None
