from __future__ import annotations

import json

import hermes_smart_router


class _DummyAgent:
    def __init__(self) -> None:
        self.model = "auto"
        self.provider = "copilot"
        self.aux_failures: list[tuple[str, str]] = []

    def _emit_auxiliary_failure(self, task: str, exc: BaseException) -> None:
        self.aux_failures.append((str(task), str(exc)))


def test_pre_llm_call_routes_user_and_prints_compact_model(monkeypatch, capsys) -> None:
    agent = _DummyAgent()

    monkeypatch.setattr(hermes_smart_router, "_find_active_agent_from_stack", lambda: agent)
    monkeypatch.setattr(
        hermes_smart_router.tools,
        "route",
        lambda _: json.dumps({"selected_provider": "copilot", "selected_model": "gpt-5-mini"}),
    )

    result = hermes_smart_router._pre_llm_call_route(
        session_id="s1",
        user_message="hi what model are you using?",
        model="auto",
        platform="copilot",
        sender_id="user",
    )

    assert result is None
    stderr = capsys.readouterr().err
    assert "⚡gpt-5-mini" in stderr


def test_pre_llm_call_skips_auxiliary_title_generation(monkeypatch) -> None:
    called = {"route": 0}
    agent = _DummyAgent()

    def _fake_route(_: dict) -> str:
        called["route"] += 1
        return json.dumps({"selected_provider": "copilot", "selected_model": "gpt-5-mini"})

    monkeypatch.setattr(hermes_smart_router, "_find_active_agent_from_stack", lambda: agent)
    monkeypatch.setattr(hermes_smart_router.tools, "route", _fake_route)

    result = hermes_smart_router._pre_llm_call_route(
        session_id="s2",
        user_message="Generate a title for this conversation",
        model="auto",
        platform="copilot",
        sender_id="assistant",
    )

    assert result is None
    assert called["route"] == 0
    assert agent.model == "gpt-5-mini"


def test_pre_llm_call_without_user_message_still_forces_concrete_model(monkeypatch) -> None:
    agent = _DummyAgent()
    monkeypatch.setattr(hermes_smart_router, "_find_active_agent_from_stack", lambda: agent)

    result = hermes_smart_router._pre_llm_call_route(
        session_id="s3",
        user_message=None,
        model="auto",
        platform="copilot",
    )

    assert result is None
    assert agent.model == "gpt-5-mini"


def test_aux_warning_filter_suppresses_known_title_unsupported_model(monkeypatch) -> None:
    agent = _DummyAgent()
    monkeypatch.setattr(hermes_smart_router, "_find_active_agent_from_stack", lambda: agent)

    # Install filter via hook execution path.
    hermes_smart_router._pre_llm_call_route(
        session_id="s4",
        user_message="hello",
        model="auto",
        platform="copilot",
        sender_id="user",
    )

    # Known noisy case should be suppressed.
    agent._emit_auxiliary_failure("title generation", Exception("HTTP 400: The requested model is not supported."))
    assert agent.aux_failures == []


def test_aux_warning_filter_keeps_other_failures(monkeypatch) -> None:
    agent = _DummyAgent()
    monkeypatch.setattr(hermes_smart_router, "_find_active_agent_from_stack", lambda: agent)

    hermes_smart_router._pre_llm_call_route(
        session_id="s5",
        user_message="hello",
        model="auto",
        platform="copilot",
        sender_id="user",
    )

    # Non-title or non-matching errors should still surface.
    agent._emit_auxiliary_failure("background review", Exception("HTTP 429 rate limited"))
    assert len(agent.aux_failures) == 1
