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
| Core contract commit | `beda0affe0dcc54c1a4e224bed26fbcd85e9184c` |
| Core package version | `2.0.0a1` |
| Consumer merge commit | `d8bf9c2b74a1b69ae39de16d449e674a66da7f44` |
| Consumer pull request | [samsarix-integration-examples#6](https://github.com/Deathcharge/samsarix-integration-examples/pull/6) |
| Consumer package version | `0.2.3` |
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
connection. When the client provides a progress token, a successful call emits exactly
two token-correlated, strictly increasing, content-free phases before its terminal
response. Cancellation emits only the completed validation phase, closes progress before
tool cleanup, and refuses the cleanup-time update. The consumer asserts that neither
source secrets nor resolved workspace paths occur in protocol output.

The consumer's merged
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/d8bf9c2b74a1b69ae39de16d449e674a66da7f44/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@beda0affe0dcc54c1a4e224bed26fbcd85e9184c`;
the installed public package reports Core version `2.0.0a1`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The consumer suite completed locally on Windows with Python 3.11.9:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest -q          -> 29 passed, 91.35% branch coverage
python -m bandit -q -r src   -> passed
python -m build              -> isolated wheel and sdist passed
python -m twine check <artifacts> -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies
resolved from their exact public Git commits. Import metadata resolved to `0.2.3`
and retained the exact Core commit requirement. Outside the source checkout, the
installed `samsarix-redaction-mcp` CLI completed a real redaction over stdio,
published a sanitized artifact, emitted exactly two token-correlated progress
notifications, and exposed neither the seeded secret nor the resolved workspace
path in protocol output.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.3-py3-none-any.whl` | 17,336 | `c71bfadcfd66cc62d6c88051c0653238a2514946590ca35f774c6d62048145e7` |
| `samsarix_integration_examples-0.2.3.tar.gz` | 28,141 | `4a8d0efde71aceb85c4c0b53e2dbdad9a60c203dcd7aada4cad59686b9b58cea` |

CodeRabbit completed its independent PR review successfully with no actionable
findings. The consumer's [GitHub Actions run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30730300881)
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
- Exercise the same contract from an independently operated desktop client.
- Record an independently operated deployment or downstream repository before
  claiming production adoption.
- Use consumer demand, not framework parity, to decide whether dataclass, enum,
  or constrained-value schemas belong in Core.
