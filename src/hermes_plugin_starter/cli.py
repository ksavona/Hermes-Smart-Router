from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_router_config


def default_config_path() -> Path:
    return Path.home() / ".hermes" / "plugins" / "hermes-smart-router" / "router_config.yaml"


def cmd_setup(config_path: Path) -> int:
    cfg = load_router_config(config_path)
    print("Hermes Smart Router setup complete.")
    print(f"Config: {config_path}")
    print(f"Routing mode: {cfg.settings.routing_mode.value}")
    print(f"Providers configured: {len(cfg.providers)}")
    return 0


def cmd_doctor(config_path: Path) -> int:
    cfg = load_router_config(config_path)
    print("Hermes Smart Router diagnostics")
    print(f"Config loaded: {config_path}")
    print(f"Tier count: {len(cfg.tiers)}")
    enabled = [p.id for p in cfg.providers if p.enabled]
    print(f"Enabled providers: {', '.join(enabled) if enabled else 'none'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-smart-router")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to router config yaml",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Create/migrate config and prepare defaults")
    sub.add_parser("doctor", help="Run baseline diagnostics")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        return cmd_setup(args.config)
    if args.command == "doctor":
        return cmd_doctor(args.config)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
