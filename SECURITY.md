# Security policy

SDM handles untrusted input all the time (web addresses, file names, server replies, browser
messages), so security reports are very welcome.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Use GitHub's private reporting
instead: on this repository, open the **Security** tab and choose **Report a vulnerability**.

Include what an attacker could do, the steps to reproduce it, and the SDM version
(Help > About SDM). You'll get an answer as soon as possible; SDM is maintained by volunteers,
so please allow a few days.

## Supported versions

Security fixes go into the latest release only.

## What SDM promises

The rules SDM follows (no local web server, a network policy against requests to your own
computer and local network, strict checks of browser messages, never running downloaded files,
no secrets in logs) and the tests that check them are listed in the
[security model](docs/architecture/security-model.md).
