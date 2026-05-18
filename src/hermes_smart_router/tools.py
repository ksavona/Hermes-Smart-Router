"""Tool handlers for Hermes Smart Router."""
import json
import sys
from dataclasses import asdict
from .plugin import HermesSmartRouterPlugin, resolve_config_path

def route(args: dict, **kwargs) -> str:
    """Hermes tool handler for routing a prompt."""
    prompt = args.get("prompt", "")
    context = args.get("context", {}) or {}
    config_path = resolve_config_path(context)

    plugin = HermesSmartRouterPlugin(config_path=config_path)
    try:
        decision = plugin.route(prompt, context)
        # Convert dataclass to dict and handle enums
        result = asdict(decision)
        for key, value in result.items():
            if hasattr(value, 'value'):  # enum
                result[key] = value.value
        return json.dumps(result)
    except Exception as e:
        print(f"[ROUTE] ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return json.dumps({"error": str(e)})
