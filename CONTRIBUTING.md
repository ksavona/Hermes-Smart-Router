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

## Release checklist

- Bump version in `pyproject.toml` and `manifest.yaml`.
- Verify one-line installer URL is correct.
- Tag release in GitHub.
