from datetime import UTC, datetime

from hermes_plugin_starter.health import apply_error_to_provider_state, interpret_provider_message
from hermes_plugin_starter.models import ProviderState, ProviderType


def test_interpret_subscription_limit_message() -> None:
    result = interpret_provider_message("Premium request limit reached. Try again tomorrow.")
    assert result.category.value == "SUBSCRIPTION_LIMIT"
    assert result.confidence >= 90


def test_apply_error_sets_subscription_state() -> None:
    state = ProviderState(
        provider_id="codex",
        provider_name="Codex",
        provider_type=ProviderType.NORMAL,
    )
    result = interpret_provider_message("weekly limit exceeded")
    updated = apply_error_to_provider_state(state, result, now=datetime.now(tz=UTC))
    assert updated.status.value == "SUBSCRIPTION_LIMIT"
    assert updated.next_probe_at is not None
