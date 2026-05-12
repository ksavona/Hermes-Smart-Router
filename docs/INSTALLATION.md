# Installation

## User install (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/ksavona/Hermes-Smart-Router/main/scripts/install.sh | bash
```

The installer performs clone, dependency install, plugin registry update, and setup diagnostics.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/ksavona/Hermes-Smart-Router/main/scripts/uninstall.sh | bash
```

## Environment Variables

- `HERMES_PLUGIN_REPO_URL`: Git URL for plugin source
- `HERMES_PLUGIN_BRANCH`: Branch or tag to install from
- `HERMES_HOME`: Hermes home directory (default: `~/.hermes`)
- `HERMES_PLUGIN_NAME`: Installed plugin directory name

## Registration details

- Plugin path: `~/.hermes/plugins/hermes-smart-router`
- Registry file: `~/.hermes/plugins/registry.yaml`
- Hermes config key (if missing, installer appends): `plugins_registry`

## Verification

1. Confirm files exist in `~/.hermes/plugins/<plugin-name>`.
2. Confirm registry contains `hermes-smart-router` entry.
3. Restart Hermes.
4. Check Hermes logs for plugin registration success.
