"""The browser bridge (ADR-0014): Chrome's native messaging host and its pipe to the app.

`protocol` frames and checks messages, `pipe` carries them to the running app with a
per-user key, `host` is the program Chrome starts, and `install` registers it. Every message
is untrusted input and is validated before it reaches the window.
"""
