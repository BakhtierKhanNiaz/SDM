# IDM behavior observations

Facts seen in controlled tests of IDM. Hypotheses go in their own labelled field and are
never mixed with what was seen.

**No observations recorded yet.**

## Planned: M2 comparison scenarios

Each scenario will be served by a local test server, so IDM and SDM see identical responses.
These are planned tests, not results.

| # | Scenario | Question for IDM |
|---|---|---|
| 1 | `Content-Disposition: attachment; filename="Report 2026.pdf"` on a URL ending in `/dl?id=7` | Which name does IDM use? |
| 2 | The same file downloaded twice | Does IDM ask, rename (how?), or overwrite? |
| 3 | Server answers `404 Not Found` | What does IDM show? Does it retry? |
| 4 | `302` redirect to `/files/archive.zip` | Does IDM name the file after the final URL? |
| 5 | No `Content-Length` (size unknown) | How are size, progress and time left shown? |
| 6 | Server promises N bytes, then closes halfway | Does IDM detect it? Retry? Keep a partial file? |

## How to record an observation

Copy this template, give it the next number, and fill in every field. Write "unknown" rather
than guessing.

```markdown
### OBS-001: <short title>

- **Date / IDM version:** 2026-MM-DD / 6.42 build 22
- **Setup:** settings changed from default, network conditions, test server and file used
- **Steps:** numbered user actions
- **Observed result:** exactly what appeared or happened (UI text, files written, timing)
- **Evidence:** screenshot or log path under docs/research/evidence/
- **Hypotheses (not verified):** possible explanations, each marked as a guess
- **Open questions:** what to test next
```
