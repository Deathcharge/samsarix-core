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
3. installs the wheel without dependencies in a fresh environment and imports both
   the Samsarix API and compatibility namespace;
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
git tag -a v2.0.0a1 -m "Samsarix Core 2.0.0a1"
git push origin v2.0.0a1
```

The push is the publication authorization. Do not reuse or force-move a released tag.
Alpha, beta, release-candidate, and development versions are marked as prereleases and
are not selected as GitHub's latest stable release.

## Verify

Download into a new directory and verify the release, exact assets, checksums, and build
provenance:

```bash
gh release verify v2.0.0a1 --repo Deathcharge/samsarix-core
gh release download v2.0.0a1 --repo Deathcharge/samsarix-core
gh release verify-asset v2.0.0a1 samsarix_core-2.0.0a1-py3-none-any.whl \
  --repo Deathcharge/samsarix-core
sha256sum --check SHA256SUMS
gh attestation verify samsarix_core-2.0.0a1-py3-none-any.whl \
  --repo Deathcharge/samsarix-core
gh attestation verify samsarix_core-2.0.0a1.tar.gz \
  --repo Deathcharge/samsarix-core
```

Then install the verified wheel in a fresh supported Python environment and run the
documented example before recording the release as complete.

## Recovery

An immutable release is intentionally not edited in place. If a published artifact or
contract is wrong, document the issue, prepare a new version, rerun the complete gate,
and publish a new tag. Consumers can roll back by installing a previously verified
release asset or exact commit. Core stores no remote runtime state.

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
