# Architecture decision records

Each record states one decision, why it was made, and what it costs. Records are never
deleted. A changed decision gets a new record that supersedes the old one.

---

## ADR-0001: Python + PySide6 desktop application

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief asks for a Windows desktop app built with free tools, maintainable by a
  beginner, running well on an i3-8100 with 8 GB RAM and no GPU.
- **Decision:** Python with PySide6 (Qt for Python) for the UI. Use the
  `PySide6-Essentials` package (core Qt modules, including widgets) rather than full `PySide6`,
  which adds large optional modules (WebEngine, 3D, charts) that SDM doesn't need.
- **License:** PySide6 is LGPL-3.0. That's fine for personal use; we use it unmodified, as a
  library.
- **Consequences:** about 80 MB download for Qt. If a later feature needs an Addons module, we
  switch to the full `PySide6` package.

## ADR-0002: Python version policy

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief names Python 3.12 as the baseline. Only Python 3.14.7 is installed. All
  chosen dependencies ship Windows wheels for 3.12 through 3.14.
- **Decision:** Develop on 3.14 (`.python-version`). Declare `requires-python = ">=3.12"`. Ruff
  targets `py312`, so it won't suggest syntax newer than 3.12.
- **Consequences:** A feature added in 3.13 or 3.14 (a new library function, for example)
  could slip in unnoticed. Mitigation: before packaging (M10), or earlier if needed, run the tests
  on 3.12 with `uv run --python 3.12 pytest`.

## ADR-0003: uv for environments and dependencies

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** We need an isolated environment, reproducible versions, and commands that work
  in PowerShell where script execution (venv activation) is restricted.
- **Decision:** uv (MIT/Apache-2.0, already installed) manages `.venv`, dependencies and the
  `uv.lock` lockfile. Build backend: `uv_build`. Commands run through `uv run`. `link-mode =
  "copy"` because uv's cache (C:) and the project (D:) are on different drives.
- **Consequences:** Contributors need uv. `uv.lock` is committed and pins exact versions.

## ADR-0004: `src/` layout with independent packages

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief requires UI, engine, storage, scheduler and bridge to stay independent.
- **Decision:** Code lives in `src/sdm/` with one package per area. The dependency rules are in
  [system-architecture.md](../architecture/system-architecture.md); the key rule is that the
  engine never imports Qt. The `src/` layout means tests run against the installed package, not
  stray files in the project root. Placeholder folders the brief lists (`extension/chrome/`,
  `scripts/`, `tests/integration/`, `tests/security/`) are created when their first file exists,
  because Git doesn't track empty folders.
- **Consequences:** You must run `uv sync` once before the code can be imported. `uv run` does
  this automatically.

## ADR-0005: Project location outside protected folders

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** Windows Defender Controlled Folder Access blocks unrecognized programs (Python,
  uv, Git) from writing to Documents and Desktop. Changing that security setting is left to
  the user.
- **Decision:** The repository lives at `D:\Projects\SDM`.
- **Consequences:** None for the code. SDM itself will face the same block if users choose
  protected download folders (handled in M2 error reporting).
