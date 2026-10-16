# Security model

Status: **initial principles (M1).** Each rule becomes concrete code and tests in the milestone
listed.

## Trust boundaries

| Input | Trust | Where it enters |
|---|---|---|
| URLs, redirects, response headers, file contents | Untrusted | engine (M2) |
| Filenames from URLs or `Content-Disposition` | Untrusted | engine (M2) |
| Messages from the browser extension | Untrusted | bridge (M7) |
| User input in the SDM window | Trusted intent, still validated | ui |
| Local database and settings | Trusted, but must survive corruption | storage (M3) |

## Rules

1. **Protocols:** only `http` and `https`. Reject `file:`, `ftp:`, `data:`, `javascript:` and
   anything else (M2).
2. **Destinations:** requests to loopback, link-local and private-network addresses, including
   ones reached through redirects, need an explicit, documented policy (M2/M8). Re-check every
   redirect hop.
3. **Filenames:** sanitize for Windows (reserved names such as `CON`, invalid characters,
   trailing dots and spaces, path separators, `..`), keep the full path under ~260 characters,
   and never write outside the chosen download folder (M2).
4. **No overwrite by default:** existing files are never replaced silently (M2).
5. **Never execute** downloaded files, and never open them automatically.
6. **No local HTTP server.** Browser communication goes only through Chrome Native Messaging,
   restricted to SDM's own extension ID (M7).
7. **Browser messages:** a strict schema, a size limit, and only "download this URL" style
   requests. No filesystem operations, no arbitrary paths, and safe error replies that leak
   nothing (M7).
8. **Secrets:** never log cookies, tokens, authorization headers or full query strings that
   may hold credentials (all milestones).
9. **Privacy:** no browsing-history collection beyond explicit handoffs, and no data sent to
   third parties.
10. **Dependencies:** free/open-source only, with license and support checked first and
    versions pinned in `uv.lock`.

## Environment notes

- Windows Controlled Folder Access is on. Writes to protected folders fail, and SDM must
  report that clearly rather than retrying forever or losing data.
