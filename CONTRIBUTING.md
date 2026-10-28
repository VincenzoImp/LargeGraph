# Contributing

Start with a small user task or reproducible failure. For a performance change,
include graph size, semantics, RAM/disk budget, backend, cold/warm cache state and
output-quality checks. A faster result with different semantics is not the same
benchmark. Discuss large changes in an issue before rewriting the engine.

## Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --locked --extra images --extra leiden --extra validation
uv run --no-sync ruff check .
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync mypy
uv run --no-sync pytest -q -m 'not browser'
```

Python is pinned in `.python-version`; the package supports Python 3.12+.
uv maintains `.venv` and `uv.lock`. Update dependency declarations with uv and
commit the lockfile. Do not manually edit wheel hashes. End users can still use
pip; uv is the contributor workflow, not a package runtime requirement.

Browser checks:

```bash
uv sync --locked --extra images --extra leiden --extra validation --group browser
uv run --no-sync playwright install chromium
uv run --no-sync pytest -q -m browser
```

The optional `networkit` extra installs NetworKit for controlled comparisons.
The HTML asset is self-contained. Format edits with
`npx --yes prettier@3.6.2 --write src/largegraph/assets/report.html` when npm is
available. Node is not required to run or build the Python package.

## Architecture

- `api.py`, `config.py`, `workbench.py`: public workflow, validated settings, CLI.
- `artifacts.py`, `runtime.py`, `budget.py`: locking, integrity, recovery, resources.
- `prepare.py`, `cluster.py`, `aggregate.py`: disk-backed graph engine.
- `profile.py`, `hierarchy.py`, `query.py`, `export.py`: reusable graph operations.
- `layout.py`, `report.py`, `server.py`, `assets/`: bounded exploration.
- `views.py`, `validate.py`, `benchmark.py`: optional figures and research tooling.

Keep large edge lists out of Python object collections. An operation on the full
graph must state its memory, scan and disk costs. Bounded in-memory algorithms
must validate their cap. Preserve count conventions and exactness disclosures.
Changing an artifact's meaning requires incrementing its schema/algorithm key.
Avoid global plotting/RNG side effects in library entry points.

Add tests for graph invariants, recovery or meaningful user behavior. Fault
injection is appropriate for durable stages. Do not add tests that merely mirror
trivial implementation details. CI installs a clean base wheel and exercises the
bundled demo separately from the source checkout.

## Pull requests and releases

Keep commits focused. State the problem, resulting behavior, validation and any
resource or compatibility tradeoff. Do not commit generated large inputs,
workspaces, personal datasets, credentials or compiled third-party backends.
MIT licensing applies to contributions to this repository; retain attribution
when adapting third-party code. Follow the [release guide](docs/releasing.md)
for versioning, wheel checks and publishing.

## Prelaunch compatibility policy

Maintain one public CLI, one Python API and the current analysis/artifact format.
Before the first stable release, remove superseded entry points and dependency
shims directly. Do not add migration adapters, aliases or CI jobs for previous
formats or library major versions. Refuse unsupported analysis formats and ask
for a new output directory. Historical experiment records are provenance, not
a support commitment.

Python 3.12 is the baseline. Dependency lower bounds reflect the validated lock
rather than hypothetical support for older releases. Review major upgrades
independently, measure correctness and resource use, then advance the baseline
when the candidate meets the product's CPU/RAM goals. A deferred upgrade does
not imply a permanent support branch for the current library major.
