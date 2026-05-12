# Releasing

## Versioning policy

This repository uses Semantic Versioning for Git tags and release artifacts.

- Patch: fixes, docs, non-breaking cleanup
- Minor: backward-compatible features
- Major: breaking changes

## Release checklist

1. Update version in `pyproject.toml`.
2. Update version in `manifest.yaml`.
3. Update version in runtime metadata if needed.
4. Add release notes to `CHANGELOG.md`.
5. Run:

```bash
pytest -q
ruff check .
```

6. Commit the release changes.
7. Create and push a tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

8. Verify the GitHub Actions release workflow publishes artifacts.
