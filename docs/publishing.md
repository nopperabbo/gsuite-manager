# Publishing to PyPI

gsuite-manager uses [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) for secure, tokenless PyPI publishing.

## One-Time Setup (already done in CI)

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - **PyPI project name**: `gsuite-manager`
   - **Owner**: `nopperabbo`
   - **Repository**: `gsuite-manager`
   - **Workflow name**: `release.yml`
   - **Environment**: `release`
3. Create a GitHub environment named `release` in repo Settings → Environments

## How Releases Work

1. Update `version` in `pyproject.toml`
2. Update `CHANGELOG.md` with new version section
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push origin main --tags`

The `release.yml` workflow will automatically:
- Run tests
- Build the package (wheel + sdist)
- Publish to PyPI via trusted publisher (OIDC, no tokens needed)
- Create a GitHub Release with changelog and dist artifacts

## Verify

After first publish: `pip install gsuite-manager` should work.
