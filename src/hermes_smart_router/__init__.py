"""Hermes Smart Router plugin registration."""
from . import schemas, tools
from .plugin import PluginInfo
import inspect
import json
import sys
import time


_RECENT_ROUTE_KEYS: dict[str, float] = {}
_RECENT_WINDOW_SECONDS = 8.0
_AUTO_MODEL_ALIASES = {"auto"}
_DEFAULT_AUX_PROVIDER = "copilot"
_DEFAULT_AUX_MODEL = "gpt-5-mini"

# Session-scoped base model/provider used for restoring after auto routing.
_SESSION_BASE_MODEL: dict[str, str] = {}
_SESSION_BASE_PROVIDER: dict[str, str] = {}
_SESSION_LAST_ROUTED_MODEL: dict[str, str] = {}
_SESSION_LAST_ROUTED_PROVIDER: dict[str, str] = {}


def _is_auto_model(model_name: object) -> bool:
    if not isinstance(model_name, str):
        return False
    return model_name.strip().lower() in _AUTO_MODEL_ALIASES


def _find_active_agent_from_stack():
    """Best-effort resolver for the live AIAgent instance in the current hook call stack."""
    for frame_info in inspect.stack():
        try:
            maybe_self = frame_info.frame.f_locals.get("self")
            if maybe_self is None:
                continue
            if (
                maybe_self.__class__.__name__ == "AIAgent"
                and hasattr(maybe_self, "model")
                and hasattr(maybe_self, "provider")
            ):
                return maybe_self
        finally:
            # Avoid frame-reference cycles from inspect.stack()
            del frame_info
    return None


def _normalize_prompt_for_dedupe(user_message: str) -> str:
    marker = "\n\n🔄 **Routing Decision**"
    if marker in user_message:
        return user_message.split(marker, 1)[0].strip()
    return user_message.strip()


def _is_auxiliary_or_title_request(kwargs: dict, user_message: str) -> bool:
    sender_id = str(kwargs.get("sender_id", "") or "").strip().lower()
    if sender_id and sender_id not in {"user", "human", "client", ""}:
        return True

    text = str(user_message or "").strip().lower()
    if not text:
        return False

    title_markers = (
        "generate a title",
        "title generation",
        "conversation title",
        "summarize this chat title",
        "short title",
    )
    return any(marker in text for marker in title_markers)


def _apply_aux_model_override(session_id: str) -> None:
    """Force auxiliary/title requests to a concrete model instead of 'auto'."""
    agent = _find_active_agent_from_stack()
    if agent is None:
        return

    model = _SESSION_LAST_ROUTED_MODEL.get(session_id) or _DEFAULT_AUX_MODEL
    provider = _SESSION_LAST_ROUTED_PROVIDER.get(session_id) or _DEFAULT_AUX_PROVIDER

    try:
        agent.model = model
        agent.provider = provider
    except Exception:
        return


def _ensure_concrete_model_for_auto_calls(session_id: str, current_model: str) -> None:
    """Guarantee that any outbound call never uses literal 'auto' at provider layer."""
    if not _is_auto_model(current_model):
        return
    _apply_aux_model_override(session_id)


def _install_aux_warning_filter() -> None:
    """Suppress known non-critical title-generation unsupported-model noise."""
    agent = _find_active_agent_from_stack()
    if agent is None:
        return
    if bool(getattr(agent, "_hsr_aux_failure_filter_installed", False)):
        return

    original = getattr(agent, "_emit_auxiliary_failure", None)
    if not callable(original):
        return

    def _filtered(task: str, exc: BaseException):
        task_text = str(task or "").strip().lower()
        detail_text = str(exc or "").strip().lower()
        if "title" in task_text and "requested model is not supported" in detail_text:
            return
        return original(task, exc)

    try:
        setattr(agent, "_emit_auxiliary_failure", _filtered)
        setattr(agent, "_hsr_aux_failure_filter_installed", True)
    except Exception:
        return


def _pre_llm_call_route(**kwargs):
    """
    Hook: runs before every LLM call to route the prompt automatically.
    This ensures routing happens for EVERY message, not just when the model decides to use the tool.
    """
    user_message = kwargs.get("user_message")
    session_id = kwargs.get("session_id", "unknown")
    current_model = str(kwargs.get("model", "") or "")
    current_provider = str(kwargs.get("platform", "") or "")

    _install_aux_warning_filter()

    # Safety net for auxiliary/internal calls: never let provider requests go out as "auto".
    _ensure_concrete_model_for_auto_calls(session_id, current_model)

    if not user_message:
        return None

    if _is_auxiliary_or_title_request(kwargs, str(user_message)):
        # Auxiliary/title generation should not use 'auto', otherwise some backends
        # reject it (HTTP 400: requested model is not supported).
        if _is_auto_model(current_model):
            _apply_aux_model_override(session_id)
        return None

    # Respect user-selected models: auto routing only runs when active model is "auto".
    if not _is_auto_model(current_model):
        _SESSION_BASE_MODEL.pop(session_id, None)
        _SESSION_BASE_PROVIDER.pop(session_id, None)
        return None

    # Record the user's base auto model/provider for post-turn restoration.
    _SESSION_BASE_MODEL[session_id] = current_model
    _SESSION_BASE_PROVIDER[session_id] = current_provider

    normalized_message = _normalize_prompt_for_dedupe(user_message)
    if not normalized_message:
        return None

    now = time.time()
    dedupe_key = f"{session_id}:{normalized_message}"
    last_seen = _RECENT_ROUTE_KEYS.get(dedupe_key)
    if last_seen is not None and (now - last_seen) < _RECENT_WINDOW_SECONDS:
        return None
    _RECENT_ROUTE_KEYS[dedupe_key] = now

    # Infer task complexity from prompt text so routing escalates without relying on model-supplied context
    msg_lower = normalized_message.lower()
    code_keywords = (
        "write", "implement", "create", "build", "code", "function", "class",
        "script", "program", "algorithm", "debug", "fix", "refactor", "test",
        "api", "database", "sql", "html", "css", "javascript", "python",
        "rust", "go", "java", "c++", "typescript",
    )
    reasoning_keywords = (
        "explain", "why", "how", "analyze", "compare", "design", "architecture",
        "trade-off", "tradeoff", "evaluate", "reason", "think", "step by step",
        "pros and cons", "decision", "strategy", "plan", "review",
    )
    inferred_context = dict(kwargs.get("context", {}) or {})
    if any(kw in msg_lower for kw in code_keywords):
        inferred_context.setdefault("requires_code", True)
    if any(kw in msg_lower for kw in reasoning_keywords):
        inferred_context.setdefault("requires_reasoning", True)

    # Route the message
    try:
        routing_result_raw = tools.route({
            "prompt": normalized_message,
            "context": inferred_context
        })

        if isinstance(routing_result_raw, str):
            try:
                routing_result = json.loads(routing_result_raw)
            except json.JSONDecodeError:
                routing_result = {}
        elif isinstance(routing_result_raw, dict):
            routing_result = routing_result_raw
        else:
            routing_result = {}

        # Enforce router selection for this turn by mutating the active agent's
        # model/provider before API kwargs are built. Restored in post_llm_call.
        selected_model = str(routing_result.get("selected_model", "") or "")
        selected_provider = str(routing_result.get("selected_provider", "") or "")
        if selected_model:
            _SESSION_LAST_ROUTED_MODEL[session_id] = selected_model
            if selected_provider:
                _SESSION_LAST_ROUTED_PROVIDER[session_id] = selected_provider
            agent = _find_active_agent_from_stack()
            if agent is not None:
                old_model = getattr(agent, "model", None)
                old_provider = getattr(agent, "provider", None)
                try:
                    agent.model = selected_model
                    if selected_provider:
                        agent.provider = selected_provider
                    # Compact runtime output for Hermes terminal.
                    print(f"⚡{selected_model}", file=sys.stderr, flush=True)
                except Exception as exc:
                    print(f"[ROUTE-HOOK] Failed to enforce turn model: {exc}", file=sys.stderr, flush=True)
        
        return None
    
    except Exception as e:
        # Fail silently - don't break the agent if routing fails
        print(f"[ROUTE-HOOK] ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None


def _post_llm_call_restore_model(**kwargs):
    """Restore user's base auto model/provider after turn-scoped router override."""
    session_id = kwargs.get("session_id", "unknown")
    base_model = _SESSION_BASE_MODEL.get(session_id)
    base_provider = _SESSION_BASE_PROVIDER.get(session_id)
    if not base_model:
        return None

    agent = _find_active_agent_from_stack()
    if agent is None:
        return None

    try:
        agent.model = base_model
        if base_provider:
            agent.provider = base_provider
    except Exception as exc:
        print(f"[ROUTE-HOOK] Failed to restore base model: {exc}", file=sys.stderr, flush=True)
    return None


def _on_session_end_cleanup(**kwargs):
    session_id = kwargs.get("session_id", "unknown")
    _SESSION_BASE_MODEL.pop(session_id, None)
    _SESSION_BASE_PROVIDER.pop(session_id, None)
    _SESSION_LAST_ROUTED_MODEL.pop(session_id, None)
    _SESSION_LAST_ROUTED_PROVIDER.pop(session_id, None)
    return None


def _route_tool_guarded(args: dict, **kwargs):
    """Allow direct route-tool calls only while Auto mode is active."""
    session_id = str(kwargs.get("session_id", "") or "")
    base_model = _SESSION_BASE_MODEL.get(session_id, "")
    agent = _find_active_agent_from_stack()
    active_model = str(getattr(agent, "model", "") or "") if agent is not None else ""

    if not (_is_auto_model(base_model) or _is_auto_model(active_model)):
        return json.dumps(
            {
                "skipped": True,
                "reason": "manual_mode",
                "active_model": active_model,
            }
        )

    return tools.route(args, **kwargs)


def register(ctx):
    """Register the Smart Router tool with Hermes."""
    print("[ROUTER-PLUGIN] Registering Smart Router plugin...", file=sys.stderr, flush=True)

    # Keep routing hook-only to avoid model-side route-tool recursion/loop spam.
    print("[ROUTER-PLUGIN] Direct route tool disabled (hook-only mode)", file=sys.stderr, flush=True)
    
    # Register the mandatory pre-LLM-call hook (ensures routing happens for EVERY message)
    ctx.register_hook("pre_llm_call", _pre_llm_call_route)
    print("[ROUTER-PLUGIN] Registered pre_llm_call hook", file=sys.stderr, flush=True)
    ctx.register_hook("post_llm_call", _post_llm_call_restore_model)
    print("[ROUTER-PLUGIN] Registered post_llm_call hook", file=sys.stderr, flush=True)
    ctx.register_hook("on_session_end", _on_session_end_cleanup)
    print("[ROUTER-PLUGIN] Registered on_session_end hook", file=sys.stderr, flush=True)
    
    # Optionally, expose plugin metadata
    ctx.plugin_info = PluginInfo(
        name="hermes-smart-router",
        version="0.2.0",
        description="Smart model routing plugin for Hermes with tier and auto modes",
    )
    print("[ROUTER-PLUGIN] Plugin registration complete!", file=sys.stderr, flush=True)
