# Release process

Samsarix Core publishes approved GitHub releases from immutable version tags. PyPI
publication is a separate owner decision and is not performed by this repository.

## Safety boundary

The `Release` workflow accepts manual dispatches as build-only dry runs. It publishes
only for a pushed `v*` tag, requires that tag to match `samsarix_core.__version__`, and
requires the tag to point to the current default-branch head. The tag must already
exist; the workflow never creates or moves it. The publication procedure separately
requires repository release immutability to be enabled before the tag is pushed.

For a tag build, the workflow:

1. builds the wheel and source distribution with `python -m build`;
2. runs strict Twine metadata checks;
3. installs the wheel offline without dependencies in a temporary environment, verifies
   public exports and runtime behavior, and drives the documented MCP example through
   actual subprocess pipes, then runs the transactional SQLite reservation example;
4. creates a `SHA256SUMS` manifest;
5. generates GitHub Actions build-provenance attestations for both distributions; and
6. creates a GitHub release containing the distributions and checksum manifest.

GitHub documents that attestations connect artifacts to their repository, commit,
workflow, and build identity; they do not prove that the code is vulnerability-free.
Published immutable releases prevent replacement of their associated tags and assets.

## Prepare and dry-run

Before tagging:

- make the version in `pyproject.toml` and `src/samsarix_core/_version.py` identical;
- close the matching changelog entry with a date;
- merge only after the complete CI matrix and package job pass; and
- run the build-only workflow from the exact `main` commit:

```bash
gh workflow run Release --ref main
gh run list --workflow Release --limit 1
gh run watch RUN_ID --exit-status
```

Enable release immutability in the repository settings before the first tag, then verify
the setting through GitHub's repository API. This administrative check deliberately
stays outside the narrowly scoped workflow token.

## Publish

From a clean, current `main` checkout, create and push one annotated tag:

```bash
RELEASE_VERSION="<next-version>"
git tag -a "v${RELEASE_VERSION}" -m "Samsarix Core ${RELEASE_VERSION}"
git push origin "v${RELEASE_VERSION}"
```

The push is the publication authorization. Do not reuse or force-move a released tag.
Alpha, beta, release-candidate, and development versions are marked as prereleases and
are not selected as GitHub's latest stable release.

## Verify

Download into a new directory and verify the release, exact assets, checksums, and build
provenance:

```bash
RELEASE_VERSION="<published-version>"
gh release verify "v${RELEASE_VERSION}" --repo Deathcharge/samsarix-core
gh release download "v${RELEASE_VERSION}" --repo Deathcharge/samsarix-core
gh release verify-asset "v${RELEASE_VERSION}" "samsarix_core-${RELEASE_VERSION}-py3-none-any.whl" \
  --repo Deathcharge/samsarix-core
sha256sum --check SHA256SUMS
gh attestation verify "samsarix_core-${RELEASE_VERSION}-py3-none-any.whl" \
  --repo Deathcharge/samsarix-core
gh attestation verify "samsarix_core-${RELEASE_VERSION}.tar.gz" \
  --repo Deathcharge/samsarix-core
```

Then install the verified wheel in a fresh supported Python environment and run the
documented example before recording the release as complete.

### Portable installed-wheel gate

From a current source checkout (Python 3.10+), run:

```bash
python scripts/verify_distribution.py /absolute/path/to/samsarix_core-VERSION-py3-none-any.whl
```

Omit the argument only when `dist/` contains exactly one wheel. The verifier creates a
temporary virtual environment, installs the exact artifact with `--no-index --no-deps`,
runs `pip check`, and invokes both smoke scripts and the SQLite example using Python
isolated mode (`-I`) from outside the checkout. It does not change the caller's environment
or access a package index. Environment creation and subprocesses have finite deadlines; the MCP checker
kills and reaps its child on failure. No model, account, network service, or user data
is needed. Only run the checker against trusted project wheels and examples.

The gate verifies:

- canonical/legacy export identity and installed metadata version consistency;
- actual synchronous Unicode invocation, invalid-input/deadline rejection, and ordered
  batches that survive an invalid timeout;
- redacted dependency failure, fail-fast circuit rejection, one later recovery probe,
  closed state, trip/rejection metrics, and bounded runtime quiescence;
- real MCP initialization before discovery/calls, UTF-8 and escaped-newline round-trip,
  synchronous results, invalid-input error logging with content-free fields, async
  progress correlation/order, and clean EOF shutdown without extra stdout.
- real temporary SQLite stock mutation, duplicate replay, conflicting-key rejection,
  replay after runtime recreation, and final stock verification before cleanup.

Package CI runs this gate on Linux, Windows, and macOS at Python 3.10 and 3.14;
the full unit suite additionally covers Python 3.10 through 3.14 on Linux. The
subprocess journey follows the [MCP stdio transport contract](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
This is package/OS-pipe compatibility evidence, not a signed-in desktop-client test,
network-transport certification, or a performance guarantee.

## Recovery

An immutable release is intentionally not edited in place. If a published artifact or
contract is wrong, document the issue, prepare a new version, rerun the complete gate,
and publish a new tag. Consumers can roll back by installing a previously verified
release asset or exact commit. Core stores no remote runtime state.

## Published evidence: v2.0.0a7

The finite-deadline validation fix in `2.0.0a8` is not in this artifact. The current
checkout's expanded gate requires that fix and therefore is not a passing gate for a7.
The historical verification below used the earlier gate, before deadline regressions
were added. Do not replace the immutable a7 files to incorporate newer changes.

The per-tool circuit-breaker alpha was published on 2026-08-11 as an immutable
GitHub prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a7`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a7) |
| Tagged commit | `766189a035c8a076a2b23f10b28576af586d5474` |
| Annotated tag object | `56308ee653c91a6ea35e410165a519b61297390b` |
| Release workflow | [run `31460562784`](https://github.com/Deathcharge/samsarix-core/actions/runs/31460562784) |
| Build-only dry run | [run `31460435905`](https://github.com/Deathcharge/samsarix-core/actions/runs/31460435905) |
| Exact-main CI | [run `31460476424`](https://github.com/Deathcharge/samsarix-core/actions/runs/31460476424) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a7-py3-none-any.whl` | 51,136 | `2aaa2980e7c1d69445402eab8d0b34a620f2bf829c1311e4f2f6cc57940f7c29` |
| `samsarix_core-2.0.0a7.tar.gz` | 136,538 | `c2b407e84e12cbe956a45c528a528fc142f41bc7767a3986af80c849bc0cb409` |
| `SHA256SUMS` | 200 | `403795bad3323aebed67b129443e396075c73cd28246bce0e9954474edac5b41` |

`gh release verify` confirmed the immutable release, and `gh release verify-asset`
confirmed all three freshly downloaded assets. The downloaded manifest independently
matched both distribution digests. `gh attestation verify` validated SLSA provenance
for the wheel and source distribution while identifying this public repository,
`.github/workflows/release.yml`, tag ref `refs/tags/v2.0.0a7`, source commit
`766189a035c8a076a2b23f10b28576af586d5474`, and a GitHub-hosted runner.

A fresh Python 3.11.9 environment installed the downloaded wheel without dependencies
and reported no broken requirements. Both public namespaces and distribution metadata
reported `2.0.0a7` from the fresh environment's `site-packages`.

Evidence correction, 2026-08-31: the smoke script shipped at the a7 tag checked imports
and model construction only. The earlier wording overstated that script's behavioral
coverage. On this date, a freshly downloaded a7 wheel with the unchanged digest above
passed `gh release verify-asset` and the expanded portable gate on Windows/Python 3.11.9.
That new execution proved failure/open/recovery behavior, sync and batch invocation,
input validation, and the real Unicode/progress/EOF MCP subprocess journey. The
verification scripts were from the pre-deadline-fix checkout; the immutable a7 artifact was
not modified. This is
GitHub distribution, provenance, and clean-wheel behavior evidence, not PyPI
publication, a stable-API declaration, a security audit, third-party production
adoption, or an SLA.

## Published evidence: v2.0.0a6

The per-tool rate-limit alpha was published on 2026-08-10 as an immutable GitHub
prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a6`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a6) |
| Tagged commit | `f09e77877b04500aa7d23504ba21123577138543` |
| Annotated tag object | `e38fa58fcf94fac6b0525027967194f9c6d8fb64` |
| Release workflow | [run `31451329609`](https://github.com/Deathcharge/samsarix-core/actions/runs/31451329609) |
| Build-only dry run | [run `31451018128`](https://github.com/Deathcharge/samsarix-core/actions/runs/31451018128) |
| Exact-main CI | [run `31450834231`](https://github.com/Deathcharge/samsarix-core/actions/runs/31450834231) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a6-py3-none-any.whl` | 48,503 | `4e0b52c0bd72d143e8ab5cc28180f86b12fc004ef3a056d854a275d1654c7d22` |
| `samsarix_core-2.0.0a6.tar.gz` | 124,908 | `61cce7d16c659916b0fb36887c5cadd9e48f697c46f41d6f7d7f6efa42d716fe` |
| `SHA256SUMS` | 200 | `b8d701365b30f258e014aa3a46f2e491eff908598d746c04c01ac453ad84c433` |

`gh release verify` confirmed the immutable release, and `gh release verify-asset`
confirmed all three freshly downloaded assets. The downloaded manifest independently
matched both distribution digests. `gh attestation verify` validated SLSA provenance
for the wheel and source distribution while explicitly requiring this public repository,
`.github/workflows/release.yml`, tag ref `refs/tags/v2.0.0a6`, source commit
`f09e77877b04500aa7d23504ba21123577138543`, and a GitHub-hosted runner.

A fresh Python 3.11.9 environment installed the downloaded wheel without dependencies
and reported no broken requirements. Both public namespaces reported `2.0.0a6`, exposed
the same `ToolRateLimit`, and resolved from the fresh environment's `site-packages`. The
installed public example completed one call, rejected an immediate second call as
`rate_limited` with a numeric retry delay, and succeeded again after that delay. This is
GitHub distribution, provenance, and clean-wheel behavior evidence, not PyPI
publication, a stable-API declaration, a security audit, third-party production
adoption, or an SLA.

## Published evidence: v2.0.0a5

The lifecycle-observability alpha was published on 2026-08-02 as an immutable GitHub
prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a5`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a5) |
| Tagged commit | `60fa5554d8ef4625dc803751cc4bd34cf757e094` |
| Annotated tag object | `a5b64aac040f87e0746e987e7c773a65a6557f26` |
| Release workflow | [run `30746440097`](https://github.com/Deathcharge/samsarix-core/actions/runs/30746440097) |
| Build-only dry run | [run `30746407482`](https://github.com/Deathcharge/samsarix-core/actions/runs/30746407482) |
| Exact-main CI | [run `30746378277`](https://github.com/Deathcharge/samsarix-core/actions/runs/30746378277) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a5-py3-none-any.whl` | 46,592 | `a883741055ef00a38ca01a93a41e761a419d7070210e3f94fe8cc69da8e6ab27` |
| `samsarix_core-2.0.0a5.tar.gz` | 115,681 | `b7d86c52a30924b5dc158d576589134054ffb334944ca3ed832735c45383c893` |
| `SHA256SUMS` | 200 | `ee8decc978e7894c68e65d1ae7fdef932c79c41c56d25914e68f9c1403cbf139` |

`gh release verify` confirmed the immutable release, and `gh release verify-asset`
confirmed all three freshly downloaded assets. The downloaded manifest independently
matched both distribution digests. `gh attestation verify` validated SLSA provenance
for the wheel and source distribution while explicitly requiring the public release
workflow, tag ref, source commit, and GitHub-hosted runner.

A fresh Python 3.14.6 environment installed the downloaded wheel without dependencies
and reported no broken requirements. An installed-package probe invoked a real tool and
received correlated `started` and `success` lifecycle events without retaining the
private argument in their serialized metadata. Both public namespaces reported
`2.0.0a5`, and the import resolved to the fresh environment's `site-packages`. This is
GitHub distribution, provenance, and clean-wheel behavior evidence, not PyPI
publication, a stable-API declaration, a security audit, third-party production
adoption, or an SLA.

## Published evidence: v2.0.0a4

The per-tool bulkhead alpha was published on 2026-08-02 as an immutable GitHub
prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a4`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a4) |
| Tagged commit | `27c871942b0e90d8303d212b438d5251cb28d43f` |
| Annotated tag object | `ff2ce612186ed60f27f5de027c67db7d8a1d335e` |
| Release workflow | [run `30744216376`](https://github.com/Deathcharge/samsarix-core/actions/runs/30744216376) |
| Build-only dry run | [run `30744149615`](https://github.com/Deathcharge/samsarix-core/actions/runs/30744149615) |
| Exact-main CI | [run `30744070502`](https://github.com/Deathcharge/samsarix-core/actions/runs/30744070502) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a4-py3-none-any.whl` | 45,262 | `25c91cb597728db18c822da9494de5c64e4747d86519ee5d8eedae01b2570e0d` |
| `samsarix_core-2.0.0a4.tar.gz` | 107,730 | `b215462cc741f7c7da4d487e6e00768ca4cb44862c20e78f7708121a5e4aa40f` |
| `SHA256SUMS` | 200 | `45c818e9be236d845b4c909d2b843bd56bf03ab189429f83c4d20f053de3e83e` |

`gh release verify` confirmed the immutable release, and `gh release verify-asset`
confirmed all three downloaded assets. The downloaded manifest independently matched
the wheel and source-distribution digests. `gh attestation verify` validated one SLSA
provenance statement covering both distributions. Its certificate and predicate bind
the public repository, `.github/workflows/release.yml`, tag `v2.0.0a4`, GitHub-hosted
run `30744216376`, and source commit `27c871942b0e90d8303d212b438d5251cb28d43f`;
the signature has a public Sigstore transparency-log timestamp.

A fresh Python 3.11.9 environment installed the downloaded wheel without dependencies
and reported no broken requirements. An installed-package behavioral probe registered
one tool with `max_concurrency=1`, queued a second call to it, and completed an unrelated
tool through the remaining global slot. All three calls succeeded in input order, both
public namespaces reported `2.0.0a4`, and final pending/in-flight metrics were zero.
This is GitHub distribution and provenance evidence, not PyPI publication, a stable-API
declaration, a security audit, third-party production adoption, or an SLA. The independent
consumer now pins the post-release lifecycle commit while its installed metadata remains
`2.0.0a4`; consumers can roll back to this verified release.

## Published evidence: v2.0.0a3

The runtime-admission alpha was published on 2026-08-02 as an immutable GitHub
prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a3`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a3) |
| Tagged commit | `8e3d9460709a21b84934bc64e975824ca1882046` |
| Release workflow | [run `30741229489`](https://github.com/Deathcharge/samsarix-core/actions/runs/30741229489) |
| Build-only dry run | [run `30741086085`](https://github.com/Deathcharge/samsarix-core/actions/runs/30741086085) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a3-py3-none-any.whl` | 44,424 | `dc32cf61d806668ad8528ca7b19beabbd125a1f98de56f527052433e2cb43c34` |
| `samsarix_core-2.0.0a3.tar.gz` | 102,420 | `198ab9be86659a45d9ba8007aa4a1ab68408e9d89e583b52a070db8422c01432` |
| `SHA256SUMS` | 200 | `e82f75c0c5a6f9fca7d34fc2fe3ccde70ca23c32201f11dd199ec32866e59e17` |

`gh release verify` confirmed the immutable release attestation, while
`gh release verify-asset` confirmed every downloaded asset. `gh attestation verify`
validated SLSA provenance covering the wheel and source distribution. The verified
identity names `Deathcharge/samsarix-core/.github/workflows/release.yml`, tag
`v2.0.0a3`, GitHub-hosted run `30741229489`, and source commit
`8e3d9460709a21b84934bc64e975824ca1882046`; the signature has a public Sigstore
transparency-log timestamp. The tag and local `main` resolved to the same commit.

A fresh Python 3.11.9 environment installed the downloaded wheel without dependencies,
reported no broken requirements, and confirmed the public and legacy namespaces report
`2.0.0a3` plus the `busy` status. This is a GitHub distribution and provenance record,
not a PyPI publication, stable-API declaration, security audit, production-adoption
claim, or service-level commitment.

The preceding immutable `v2.0.0a2` tag failed closed during wheel smoke testing because
the release workflow contained a stale legacy-namespace version literal. Run
[`30740957122`](https://github.com/Deathcharge/samsarix-core/actions/runs/30740957122)
stopped before tag/version validation, attestation, or publication, and no GitHub release
exists for that tag. The smoke test now compares both namespaces dynamically; its
build-only run passed before `v2.0.0a3` was created. The failed tag was not moved or
deleted.

## Published evidence: v2.0.0a1

The first Samsarix-branded alpha was published on 2026-08-02 as an immutable GitHub
prerelease:

| Evidence | Value |
| --- | --- |
| Release | [`v2.0.0a1`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a1) |
| Tagged commit | `5f09432ebdb3d2b113b8fdb53112e39680ca5c25` |
| Release workflow | [run `30739840774`](https://github.com/Deathcharge/samsarix-core/actions/runs/30739840774) |
| Build-only dry run | [run `30739778395`](https://github.com/Deathcharge/samsarix-core/actions/runs/30739778395) |
| Release state | published, prerelease, immutable |

Published assets are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_core-2.0.0a1-py3-none-any.whl` | 43,818 | `8bc4b7b438bff0ab0a1586dc3300959c3410eaa6be50b3ddb674e61177b3b0e1` |
| `samsarix_core-2.0.0a1.tar.gz` | 99,218 | `fadca316836530743e411859678610c71b1cbf0c3709074ba8330d7bcc7edec7` |
| `SHA256SUMS` | 200 | `7cc9dd0ef0bb0a5fc33a9abd3378d84b8593516989f1789cbe316ffe39358d57` |

`gh release verify` confirmed GitHub's immutable release attestation, and
`gh release verify-asset` confirmed all three downloaded assets. `gh attestation verify`
validated a SLSA provenance statement covering the wheel and source distribution. Its
verified identity names `Deathcharge/samsarix-core/.github/workflows/release.yml`, tag
`v2.0.0a1`, GitHub-hosted run `30739840774`, and source commit
`5f09432ebdb3d2b113b8fdb53112e39680ca5c25`; the signature has a public Sigstore
transparency-log timestamp.

A fresh Python 3.11.9 environment installed the downloaded wheel without dependencies,
reported no broken requirements, and completed `examples/policy_gate.py`: the unscoped
call was denied with the safe `tool_denied` result and the scoped call succeeded. This
is a GitHub distribution and provenance record, not a PyPI publication, stable-API
declaration, security audit, production-adoption claim, or service-level commitment.

Primary references:

- [Python Packaging User Guide build guidance](https://packaging.python.org/en/latest/discussions/setup-py-deprecated/)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub immutable releases](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
- [`gh release create`](https://cli.github.com/manual/gh_release_create)
