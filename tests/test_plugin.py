from hermes_plugin_starter.plugin import register


def test_register_returns_expected_metadata() -> None:
    plugin = register({})
    assert plugin.name == "hermes-smart-router"
    assert plugin.version == "0.1.0"
