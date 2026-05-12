# Contributing

## Development setup

1. Clone this repository.
2. Install dependencies:

```bash
python -m pip install -e .[dev]
```

3. Run checks:

```bash
ruff check .
pytest
```

## Pull request standards

- Keep changes small and focused.
- Include tests for behavior changes.
- Update docs for any install, config, or API changes.
- Use clear commit messages.
- By contributing, you agree that your contribution is provided under the repository's current license terms.

## Release checklist

- Bump version in `pyproject.toml` and `manifest.yaml`.
- Bump runtime metadata if release version changed.
- Update `CHANGELOG.md`.
- Verify one-line installer URL is correct.
- Run `pytest -q` and `ruff check .`.
- Tag release in GitHub.
