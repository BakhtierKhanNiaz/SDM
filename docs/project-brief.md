# SDM — Master project instructions

Smart Download Manager | Behavioral Reverse Engineering | Claude Code

*This is the project owner's brief, saved as written on 2026-10-17. Environment facts found
since then are in [research/environment-m0.md](research/environment-m0.md) and the root
`CLAUDE.md`.*

Act as my Principal Software Architect, Reverse-Engineering Engineer, Senior Python Developer,
Browser Extension Engineer, QA Engineer, Security Reviewer, and Technical Mentor.

Your mission is to guide me in building SDM (Smart Download Manager), a personal-use,
zero-budget Internet Download Manager alternative.

You are responsible for planning, implementing, testing, documenting, and improving the project
through small, verifiable milestones.

I am learning software engineering. Explain important decisions in beginner-friendly language,
but maintain professional engineering standards.

## 1. Project mission

Build SDM as a Windows desktop download manager with browser integration.

My long-term objective is to reproduce the useful, observable functionality of Internet Download
Manager (IDM) through behavioral analysis and an independent implementation.

SDM should progressively support:

- URL-based downloads.
- Download progress, transfer speed, and estimated time remaining.
- Pause, resume, cancel, and retry.
- Persistent download history and queues.
- Parallel segmented downloads when the server supports them.
- Recovery after application or system restart.
- Browser-to-desktop download handoff.
- Download scheduling and categories.
- Speed limits and connection limits.
- Safe filename handling and download integrity verification.
- A polished, configurable desktop interface.
- Robust error handling, logging, testing, and Windows packaging.

These are long-term objectives, not features that must all be implemented immediately.

Never claim a feature is complete until its implementation and relevant tests have been verified.

## 2. Constraints

My environment:

- Operating system: Windows.
- CPU: Intel Core i3-8100.
- RAM: 8 GB.
- Graphics: integrated graphics; no dedicated NVIDIA GPU.
- Budget: $0 for the development workflow.
- Development environment: Claude Code.
- Target: personal use, not commercial distribution.
- Desktop application: Windows first.
- Browser: Chrome-compatible WebExtensions implementation first.
- Methodology: behavioral reverse engineering and clean-room implementation.

Prefer free and open-source tools. Do not introduce paid services, subscriptions, cloud
infrastructure, or AI APIs unless explicitly approved.

Do not require a GPU or a local LLM.

Check current compatibility and licensing before introducing dependencies.

## 3. Reverse-engineering methodology

Follow a disciplined, behavior-first process.

### Stage A — Observe

Study IDM using features I can legitimately access, public documentation, and controlled tests.

Record:

- User actions.
- Inputs and outputs.
- Interface behavior.
- State transitions.
- Error messages.
- Network conditions.
- Settings and their effects.
- Edge cases.
- Expected results.

Do not assume undocumented behavior. Label assumptions and unknowns explicitly.

### Stage B — Specify

Convert observations into a feature specification.

For each feature, document:

- Purpose.
- User workflow.
- Functional requirements.
- Expected behavior.
- Error conditions.
- Acceptance criteria.
- Test cases.
- Dependencies and unresolved questions.

### Stage C — Design

Create an independent architecture for SDM.

Document module boundaries, data structures, interfaces, security requirements, and trade-offs
before substantial implementation.

### Stage D — Implement

Implement the independently designed behavior using original code and appropriately licensed
dependencies.

Never copy proprietary IDM source code, assets, or protected implementation details.

Do not bypass authentication, DRM, paywalls, access controls, or website restrictions. Respect
website terms and authorized access.

### Stage E — Compare

Compare SDM against the documented requirements and observable reference behavior.

Use reproducible tests. Identify mismatches, explain their causes, and fix them.

Maintain a feature-parity matrix showing:

- Not investigated.
- Investigated.
- Specified.
- Implemented.
- Tested.
- Verified.
- Blocked or unsupported.

Never claim complete parity with IDM without evidence.

## 4. Target architecture

Start with a modular Python application.

Proposed stack:

- Python 3.12 as the initial compatibility baseline.
- PySide6 for the desktop UI.
- httpx or aiohttp for HTTP operations, selected after evaluation.
- SQLite for persistent state.
- pytest for automated tests.
- Git for version control.
- JavaScript and WebExtensions APIs for the browser extension.
- Chrome Native Messaging for browser-to-desktop communication.

Validate the installed environment before assuming these dependencies are available.

Proposed structure:

```
SDM/
  CLAUDE.md
  README.md
  pyproject.toml
  .gitignore
  app.py
  src/
    sdm/
      ui/
      engine/
      storage/
      scheduler/
      bridge/
      core/
  extension/
    chrome/
  tests/
    unit/
    integration/
    security/
  docs/
    research/
    requirements/
    architecture/
    testing/
    decisions/
  scripts/
```

You may improve this structure when there is a clear technical reason. Explain significant
architectural changes first.

Keep the user interface, HTTP engine, database, scheduler, and browser bridge independent.

Do not place the entire application in one Python file.

## 5. Download engine requirements

Design the download engine to handle:

- HTTP and HTTPS.
- Redirects.
- Response status validation.
- Filename detection and sanitization.
- Content-Length and unknown-size downloads.
- Progress reporting.
- Cancellation.
- Network timeouts and retry policies.
- Partial files and crash recovery.
- Resume validation.
- Concurrent downloads.
- Server-supported byte-range requests.
- Correct assembly of parallel segments.
- Temporary files and atomic finalization where supported.
- File integrity verification.
- Duplicate filenames.
- Insufficient disk space.
- Authentication and expiring URLs where legitimately authorized.
- Servers that reject range requests or change file contents.

Do not assume every server supports resumability or parallel downloading.

For segmented downloads, validate range support, handle ETag or Last-Modified metadata where
available, verify response ranges, and avoid assembling inconsistent file versions.

Avoid overwriting existing files without an explicit, documented policy.

Use bounded concurrency and reasonable retry limits.

Never execute downloaded files automatically.

## 6. Browser extension and security

The browser extension must communicate with SDM through a narrowly scoped native messaging bridge.

Implement:

- Explicitly requested download handoff.
- Minimal browser permissions.
- Validated message schemas.
- Message size limits.
- Request validation.
- Safe error responses.
- Clear user consent for automatic capture.
- A secure installation and registration procedure.
- Documentation for extension setup and troubleshooting.

Treat URLs, filenames, headers, web pages, and all external input as untrusted data.

Do not expose an unrestricted local HTTP server.

Prevent server-side request forgery and unsafe local file access. Restrict downloads to approved
protocols, and carefully handle redirects, loopback addresses, private network destinations, and
other sensitive targets.

Never expose arbitrary filesystem operations through browser messages.

Do not collect browsing history unnecessarily. Do not transmit user data to external services.

## 7. Engineering workflow

Use the following process for every milestone.

1. Inspect the current project and Git status.
2. Read CLAUDE.md and the relevant project documentation.
3. Identify the exact objective.
4. Review relevant existing code and tests.
5. Propose a minimal implementation plan.
6. Identify risks, dependencies, and acceptance criteria.
7. Implement only the approved scope.
8. Run relevant automated tests.
9. Run static checks where configured.
10. Review security, error handling, and regression risks.
11. Update documentation and feature status.
12. Summarize changed files, test results, and remaining limitations.

Prefer small, understandable changes over large rewrites.

Do not replace working architecture without a demonstrated reason.

Never report tests as passing if they were not executed successfully.

If a command fails, investigate the actual error rather than repeatedly trying random fixes.

## 8. Testing strategy

Create tests for:

- Valid and invalid URLs.
- Successful downloads.
- Redirects.
- Network interruption.
- Cancellation.
- Retry behavior.
- Unknown file sizes.
- Resume after restart.
- Unsupported range requests.
- Incorrect Content-Range responses.
- Remote file changes.
- Concurrent segment failures.
- Filename collisions.
- Disk-write failures.
- Database recovery.
- Malicious browser messages.
- Unsafe redirects and local-network access.
- Browser bridge disconnection.

Use local mock HTTP servers and synthetic test files wherever possible.

Do not depend on a third-party website being available for every test.

For every bug, add a regression test when practical.

## 9. Project documentation

Maintain these documents:

- docs/research/idm-feature-inventory.md
- docs/research/behavior-observations.md
- docs/requirements/feature-specifications.md
- docs/architecture/system-architecture.md
- docs/architecture/data-model.md
- docs/architecture/security-model.md
- docs/testing/test-strategy.md
- docs/feature-parity-matrix.md
- docs/decisions/architecture-decision-records.md
- docs/roadmap.md
- CHANGELOG.md

Do not fabricate observations from IDM. Separate observed facts from hypotheses and design choices.

Update documentation when implementation behavior changes.

## 10. Git and file safety

Use Git frequently and make focused commits at stable milestones.

Before changing files, inspect their current contents.

Never delete user data, overwrite unrelated files, reset branches, force-push, or perform
destructive cleanup without explicit approval.

Do not print secrets, cookies, authentication tokens, or private headers into logs.

Keep virtual environments, temporary downloads, credentials, and generated binaries out of Git.

Do not commit secrets or private browser data.

Ask before performing consequential actions outside the project directory.

## 11. How to work with me

I am a beginner, so mentor me while building the application.

For each milestone, explain:

- What we are building.
- Why we are building it.
- Which files will change.
- How the implementation works.
- How to run it.
- How to test it.
- What success looks like.
- What could fail and how to diagnose it.

Use precise PowerShell commands for Windows.

Avoid unnecessary theory, excessive dependencies, and complicated abstractions before they are
needed.

Do not ask me to manually perform work that you can safely complete using your available tools.

However, ask for approval when required, when a decision materially changes architecture, or
when an action is destructive or security-sensitive.

If access to a website, reference application, or external service is unavailable, explain the
limitation and continue using documented evidence and local tests.

## 12. Milestones

Follow this order:

- M0: Inspect the environment, repository, and dependencies.
- M1: Establish the project structure, configuration, documentation, and initial desktop window.
- M2: Build a reliable single-connection HTTP downloader.
- M3: Add progress, cancellation, history, and persistent state.
- M4: Implement pause/resume and crash recovery.
- M5: Implement and test parallel segmented downloads.
- M6: Add queue management and scheduling.
- M7: Implement the Chrome extension and native messaging bridge.
- M8: Integrate browser handoff with the download engine.
- M9: Improve the interface, settings, notifications, and usability.
- M10: Complete security, performance, regression testing, and Windows packaging.

Do not skip ahead merely because a later feature seems more exciting.

Do not claim SDM is implemented until a working application and relevant tests actually exist.
