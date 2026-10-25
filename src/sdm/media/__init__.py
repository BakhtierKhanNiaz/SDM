"""Media tools SDM runs as separate programs (M12, ADR-0020): ffmpeg, and later yt-dlp.

Pure logic only: finding the tools, building their command lines and reading their progress.
The UI runs them; nothing here imports Qt or the engine.
"""
