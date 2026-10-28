# Release guide

## Prepare

1. Update `src/largegraph/_version.py`, `CITATION.cff` and `CHANGELOG.md`.
2. Run locked lint, formatting, API type checks and unit/integration/browser tests.
3. Confirm fresh-base-wheel installation and a demo from outside the checkout.
4. Check benchmark claims against the retained measurements.
5. Confirm docs describe actual scope and current platform test evidence.

```bash
uv sync --locked --extra images --extra leiden --extra validation --group browser
uv run --no-sync ruff check .
uv run --no-sync ruff format --check src tests
uv run --no-sync mypy
uv run --no-sync pytest -q
uv build
uv run --no-sync twine check --strict dist/*
uv venv /tmp/largegraph-release-check
uv pip install --python /tmp/largegraph-release-check/bin/python dist/*.whl
```

Run `largegraph demo` from a temporary directory with that environment's
entry point. The package must contain HTML/demo assets and its license; it must
not include cached graphs, `.venv`, external binaries or benchmark inputs.
Install the sdist in a separate clean environment too. Wheels are pure Python;
third-party packages supply the native engines.

## GitHub

Create a version tag and a GitHub prerelease for a beta, attaching wheel, sdist
and SHA-256 checksums. Link an interactive example, quickstart and raw resource
evidence. A GitHub wheel is usable before PyPI setup. Verify installation and complete user workflows.

## PyPI and TestPyPI

The `publish.yml` workflow uses PyPI Trusted Publishing (OIDC), with no long-lived
upload token stored in the repository. The owner must create an account and
configure a pending publisher or an existing project's publisher:

| Setting | Value |
| --- | --- |
| PyPI project | `largegraph` |
| GitHub owner | `VincenzoImp` |
| GitHub repository | `LargeGraph` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` (or `testpypi` on TestPyPI) |

GitHub environments should use the corresponding names. Trigger the workflow
manually from the release tag with index `testpypi`, inspect the result and test
installation; then trigger `pypi`. The workflow rebuilds and validates artifacts,
publishes with provenance attestations and runs only when explicitly dispatched.
PyPI names/versions are immutable once uploaded; never reuse a published version.

Primary instructions: [PyPA publication guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
and [uv CI integration](https://docs.astral.sh/uv/guides/integration/github/).

The repository is ready to configure this path independently of whether the
maintainer has completed the external account setup. Do not describe a package
as published until its index page and a clean install have been verified.
