# Publishing DriftCTL

This maintainer guide publishes the `drift-ctl` distribution to PyPI while preserving the user-facing `driftctl` command. It is not part of ordinary installation or scanning.

## Release Model

- **PyPI distribution:** `drift-ctl`
- **Python import package:** `driftctl`
- **Terminal command:** `driftctl scan`

PyPI normalizes hyphens and underscores in project names, so `drift-ctl` and `drift_ctl` identify the same distribution name. Confirm the name is still available immediately before the first release.

## One-Time PyPI Setup

1. Create or sign in to the project's PyPI maintainer account.
2. In PyPI, add a pending GitHub Actions trusted publisher for the `drift-ctl` project:
   - Owner: `heyohjayy`
   - Repository: `DriftCTL`
   - Workflow: `publish.yml`
   - Environment: `pypi`
3. In GitHub, create an environment named `pypi` and require a maintainer review before deployment.

The pending publisher does not reserve the package name. It creates the PyPI project only when the first approved release publishes it. Do not add a long-lived PyPI API token to GitHub Secrets.

## Publish A Release

1. Update the version in `pyproject.toml` and the release notes in `CHANGELOG.md`.
2. Run the full local verification suite, including `python -m build`.
3. Commit and push the approved release changes.
4. Create and publish a GitHub release for the matching version tag, for example `v1.0.1`.
5. Approve the `pypi` environment deployment when GitHub Actions requests it.
6. Confirm the package appears on PyPI, then verify a clean installation in a new terminal:

   ```bash
   pipx install drift-ctl==1.0.1
   driftctl --help
   ```

The repository's [`publish.yml`](../.github/workflows/publish.yml) runs only when a GitHub release is published. It builds the distributions and uses PyPI Trusted Publishing, which exchanges GitHub's short-lived OIDC identity for a short-lived publishing credential.

> [!WARNING]
> Publishing a version to PyPI is permanent. Verify the version, package metadata, license, tests, and built distributions before publishing the GitHub release.
