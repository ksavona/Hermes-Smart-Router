# Security Policy

## Supported Versions

Security fixes are targeted at the latest release on the `main` branch unless stated otherwise.

## Reporting a Vulnerability

Do not open a public issue for a suspected security vulnerability.

Report it privately to the repository owner through GitHub and include:
- affected version or commit
- reproduction steps
- impact assessment
- logs or screenshots if relevant

The maintainer will review the report, confirm severity, and coordinate remediation before public disclosure when appropriate.

## Scope

Relevant security concerns include:
- credential handling
- plugin installation and update flow
- provider token exposure
- unsafe command execution
- prompt or tool injection paths
- local data leakage from logs, cache, or config files
