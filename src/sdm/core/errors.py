"""Errors SDM reports to the user. Every message must be safe to show and to log."""


class SDMError(Exception):
    """Base class for expected SDM failures (as opposed to programming bugs)."""


class InvalidURLError(SDMError):
    """The URL is malformed or uses a feature SDM refuses (e.g. ftp:, file:, embedded passwords)."""


class BlockedDestinationError(SDMError):
    """The network policy refused the destination, e.g. this computer or a private network."""


class DownloadError(SDMError):
    """A download failed.

    `retryable` tells the engine whether trying again might help (a timeout might; a 404
    won't). `retry_after` is the delay in seconds the server asked for, if any.
    """

    def __init__(
        self, message: str, *, retryable: bool = False, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
