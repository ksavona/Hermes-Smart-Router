
from pathlib import Path
import json
from hermes_smart_router.plugin import HermesSmartRouterPlugin, create_default_plugin_config
from hermes_smart_router.tools import route


def test_register_returns_plugin_with_expected_metadata(tmp_path: Path) -> None:
    config_path = tmp_path / "router_config.yaml"
    create_default_plugin_config(config_path)
    plugin = HermesSmartRouterPlugin(config_path=config_path)
    assert isinstance(plugin, HermesSmartRouterPlugin)
    assert callable(plugin.route)
    assert plugin.name == "hermes-smart-router"
    assert plugin.version == "0.2.0"


def test_register_accepts_injected_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "router_config.yaml"
    create_default_plugin_config(config_path)
    plugin = HermesSmartRouterPlugin(config_path=config_path)
    assert plugin.config_path == config_path
    assert config_path.exists()


def test_route_propagates_critical_risk_to_t5(tmp_path: Path) -> None:
    config_path = tmp_path / "router_config.yaml"
    create_default_plugin_config(config_path)
    args = {"prompt": "Need high-risk legal analysis", "context": {"risk_level": "critical", "config_path": str(config_path)}}
    result_json = route(args)
    result = json.loads(result_json)
    assert result["tier_equivalent"] == "T5"
