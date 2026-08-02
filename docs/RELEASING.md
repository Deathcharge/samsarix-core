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

Primary references:

- [Python Packaging User Guide build guidance](https://packaging.python.org/en/latest/discussions/setup-py-deprecated/)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub immutable releases](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
- [`gh release create`](https://cli.github.com/manual/gh_release_create)
