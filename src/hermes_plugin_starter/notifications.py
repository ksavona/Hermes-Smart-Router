from __future__ import annotations

from .models import RoutingDecision, RuntimeEvent


def provider_limit_message(provider: str, model: str, next_recovery: str) -> RuntimeEvent:
    return RuntimeEvent(
        level="warning",
        message=f"{provider} {model} limit reached. Removed from active routing.",
        context={"next_recovery": next_recovery},
    )


def fallback_to_tier_message(decision: RoutingDecision, reason: str) -> RuntimeEvent:
    return RuntimeEvent(
        level="warning",
        message=(
            f"Auto routing failed. Switched to Tier Routing: {decision.tier_equivalent}. "
            f"Selected: {decision.selected_provider} {decision.selected_model}."
        ),
        context={"reason": reason},
    )


def provider_recovered_message(provider: str, model: str) -> RuntimeEvent:
    return RuntimeEvent(
        level="info",
        message=f"{provider} is available again. {model} restored to active routing.",
    )
