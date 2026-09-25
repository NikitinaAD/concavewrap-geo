# Release checklist

## Before making the repository public

- [ ] CI passes on Windows and Linux with Python 3.11, 3.12, and 3.13.
- [ ] `python examples/run_examples.py` reproduces every documented scenario.
- [ ] Ruff, pytest, wheel/sdist build, Twine metadata, and clean-wheel smoke tests pass.
- [ ] README commands work from a fresh clone and use only synthetic data.
- [ ] The repository contains no private data, credentials, unrelated product names, or
      files without a clear redistribution right.
- [ ] Version `0.1.0`, changelog, citation metadata, URLs, license, and topics agree.

## Publication session

- [ ] Confirm the PyPI pending Trusted Publisher targets this repository,
      `.github/workflows/release.yml`, and the `pypi` environment.
- [ ] Make the repository public and enable required CI on `main`, with force-push and
      branch deletion disabled.
- [ ] Publish GitHub Release `v0.1.0`.
- [ ] Confirm the release workflow publishes the already-built artifacts through OIDC.
- [ ] Install `concavewrap-geo` from PyPI in fresh Windows and Linux environments and run
      `concavewrap --version` plus one documented example.
- [ ] Confirm GitHub and PyPI show Apache-2.0 and correct source, issue, and homepage URLs.
- [ ] Pin the repository only after the PyPI installation check passes.
