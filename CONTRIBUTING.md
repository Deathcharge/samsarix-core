# Contributing

Samsarix Core `2.0` is intentionally narrow while it is in alpha. Changes should
strengthen typed
local-tool declaration and invocation without silently turning the package into an
agent framework, provider SDK, network service, or sandbox.

## Development setup

```bash
python -m venv .venv
# Activate .venv for your shell.
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the full local gate:

```bash
python -m black --check src tests examples benchmarks scripts
python -m ruff check src tests examples benchmarks scripts
python -m mypy
python -m pytest
python -m build
python -m twine check --strict dist/*
python scripts/verify_distribution.py
```

The distribution verifier requires exactly one wheel in `dist/`, or an explicit wheel
path. It installs offline in a temporary environment and checks runtime and real MCP
subprocess behavior without importing from the source checkout. See
[release verification](docs/RELEASING.md) for the cross-platform gate.

New behavior needs focused tests, accurate docs, no network requirement in the
unit suite, and no reduction below the configured 90% branch-aware coverage floor.
Test public behavior with real functions rather than mocks of nonexistent systems.

## Pull requests

- Keep scope cohesive and explain the user problem.
- Preserve structured errors and exception-redaction defaults.
- Document changes to schema, timeout, cancellation, or lifecycle semantics.
- Avoid adding a runtime dependency when the standard library is sufficient.
- Do not include credentials, private data, generated build outputs, or environment files.

Use [SECURITY.md](SECURITY.md) for vulnerabilities rather than a public issue.

## License

Contributions are accepted under the repository's
[Mozilla Public License 2.0](LICENSE). By submitting a contribution for inclusion,
you represent that you have the right to license it under MPL-2.0. Copyright and
trademark information is recorded in [NOTICE](NOTICE) and
[TRADEMARKS.md](TRADEMARKS.md).
