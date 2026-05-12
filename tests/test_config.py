from pathlib import Path

from hermes_plugin_starter.config import load_router_config


def test_load_router_config_creates_defaults(tmp_path: Path) -> None:
    cfg_path = tmp_path / "router.yaml"
    cfg = load_router_config(cfg_path)
    assert cfg_path.exists()
    assert cfg.settings.routing_mode.value == "smart_auto"
    assert len(cfg.tiers) == 5
