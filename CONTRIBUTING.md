# Contributing to SDM

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a bug

Open an issue with:

- what you did, what you expected and what happened instead;
- your Windows version and SDM version (Help > About SDM);
- the relevant lines of SDM's log (Help > Open log folder, `sdm.log`; the browser helper writes
  `bridge-host.log`). Addresses in the log have their query strings removed, but check that
  nothing private remains before posting.

Security problems: please follow [SECURITY.md](SECURITY.md) instead.

## Making a change

1. Install [uv](https://docs.astral.sh/uv/), clone the repository and run `uv sync`.
2. Create a branch for your change.
3. Keep changes small and focused, and add a test for every fix or feature
   (`tests/unit`, `tests/integration` with the local `MockServer`, or `tests/security`).
4. Before opening a pull request, run every check:

   ```powershell
   uv run python scripts/check_all.py
   ```

   It runs `ruff check`, `ruff format --check`, all Python tests and the extension tests
   (`node --test` in `extension/`, Node.js 20 or newer).

## Ground rules

These keep SDM safe and independent; pull requests that break them can't be merged:

- **Clean room:** never copy, decompile or disassemble code, assets or protected details of
  other download managers. Observing their public behavior and documentation is fine.
- **Untrusted input:** URLs, file names, headers and browser messages are untrusted. Every new
  request path goes through the network policy (`src/sdm/engine/policy.py`).
- **No local web server,** no running downloaded files, no logging of secrets, cookies or tokens.
- **Tests use local servers and synthetic files,** never real websites.
- **Dependencies:** check the licence (it must allow Apache-2.0 distribution) and Windows
  support for Python 3.12-3.14, and record the choice in
  [the decision records](docs/decisions/architecture-decision-records.md).
- Code style: ruff decides (`uv run ruff format .`); Python 3.12 features at most.

By contributing, you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE).
