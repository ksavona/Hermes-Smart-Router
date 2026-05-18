"""Hermes root plugin compatibility entrypoint."""
from pathlib import Path
import sys

# Ensure the src layout package is importable when loaded as a directory plugin.
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

try:
    from hermes_smart_router import register  # noqa: E402,F401
except ModuleNotFoundError:
    # Fallback for plugin copies that only contain hermes_plugin_starter.
    from hermes_plugin_starter.plugin import register  # type: ignore  # noqa: E402,F401

__all__ = ["register"]
