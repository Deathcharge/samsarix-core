# Adoption evidence

This record separates package compatibility evidence from production-adoption
claims. Samsarix Core has a merged independent repository consumer; it does not
yet have a documented third-party production deployment, paid customer, usage
volume, or service-level commitment.

## Privacy-first redaction MCP consumer

Repository:
[Deathcharge/samsarix-integration-examples](https://github.com/Deathcharge/samsarix-integration-examples)

| Evidence | Value |
| --- | --- |
| Core contract commit | `37a996bf0af4b5277990f3db6a7607ea70e14349` |
| Core package version | `2.0.0a1` |
| Consumer merge commit | `dd7bfb84a40537522fbe964fb1ce0d2267586854` |
| Consumer pull request | [samsarix-integration-examples#5](https://github.com/Deathcharge/samsarix-integration-examples/pull/5) |
| Consumer package version | `0.2.2` |
| Integration Guard provenance | [`samsarix-integration-guard`](https://github.com/Deathcharge/samsarix-integration-guard) `0.2.0` at `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Orchestration provenance | [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) `0.1.0` at `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005` |
| Supported consumer Python | 3.11-3.13 |
| Compatibility owner | Samsarix LLC |
| Support level | Best effort; no SLA |

The consumer composes three independently packaged projects through public APIs:
Core provides the bounded MCP runtime, Integration Guard redacts sensitive JSON,
and Orchestration provides checkpointed recovery and idempotency. A client may
name one JSON file in a configured inbox and one artifact filename. It cannot
supply an absolute path or path separator, linked files are rejected, conflicting
artifacts are not replaced, and successful MCP results contain metadata rather
than document content or local paths. Its public `RedactionResult` `TypedDict`
also proves Core's exact, closed output schemas and result validation from an
independently packaged consumer. A deliberately blocked redaction call additionally
proves MCP client cancellation through the public stdio bridge: the consumer receives
no response for the cancelled request, the asynchronous tool stops, no output
artifact is published, runtime metrics return to zero in-flight calls with one
cancellation recorded, and a subsequent `tools/list` request succeeds on the same
connection.

The consumer's merged
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/dd7bfb84a40537522fbe964fb1ce0d2267586854/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@37a996bf0af4b5277990f3db6a7607ea70e14349`;
the installed public package reports Core version `2.0.0a1`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The consumer suite completed locally on Windows with Python 3.11.9:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest -q          -> 29 passed, 91.23% branch coverage
python -m bandit -q -r src   -> passed
python -m build --no-isolation
python -m twine check dist/* -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies
provided from their exact local commit worktrees. Import metadata resolved to
`0.2.2`, the public `RedactionResult` exposed its six required keys, and both
`samsarix-redaction-mcp --help` and
`samsarix-redaction-pipeline --help` completed successfully.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.2-py3-none-any.whl` | 17,167 | `1d838c01799d4323da96e6aaf58d8da1deaeb766820f12c2fde1ac5499705b01` |
| `samsarix_integration_examples-0.2.2.tar.gz` | 27,182 | `4d794c729293e920f16c30063a9ada232b36c7a6d2bc153dd6f7d5407f29d15a` |

The consumer's [GitHub Actions run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30727825079)
did not start its jobs: GitHub attached an account
billing/spending-limit failure before checkout, leaving zero executed steps and
no job logs. That infrastructure failure is not represented as hosted test
evidence. The workflow should be rerun after the account's Billing & plans issue
is resolved.

## Compatibility and rollback

The consumer uses an exact Git commit dependency rather than a moving branch.
Updating Core requires a consumer pull request that reruns the same privacy,
filesystem, protocol, packaging, and version checks. Until Core declares a stable
release line, compatibility is commit-specific.

Rollback is consumer-owned: stop the local MCP process, remove its client
registration, and revert the consumer dependency and adapter commit. Core itself
stores no remote state. After any required evidence retention, the operator may
remove the consumer workspace's generated artifacts and sanitized checkpoints.

## Next adoption signals

- Rerun the consumer Python 3.11-3.13 matrix after GitHub Actions billing is
  restored.
- Exercise timeout and bounded synchronous-thread quiescence through a
  consumer-owned deliberately slow synchronous tool; asynchronous MCP
  cancellation is now proven.
- Upgrade the consumer to prove progress-token correlation, monotonic phase
  updates, cancellation cutoff, and content-free progress messages.
- Record an independently operated deployment or downstream repository before
  claiming production adoption.
- Use consumer demand, not framework parity, to decide whether dataclass, enum,
  or constrained-value schemas belong in Core.
