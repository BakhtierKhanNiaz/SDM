"""Human-readable sizes, speeds and durations, shared by the command line and the window."""


def format_size(num_bytes: float) -> str:
    """1536 -> '1.5 KB'. Uses 1024-based units, as Windows Explorer does."""
    if num_bytes < 1024:
        return f"{num_bytes:.0f} bytes"
    size = num_bytes / 1024
    for unit in ("KB", "MB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_speed(bytes_per_second: float) -> str:
    """1536.0 -> '1.5 KB/s'."""
    return f"{format_size(bytes_per_second)}/s"


def format_duration(seconds: float) -> str:
    """Time left for a download: 42 -> '42 s', 125 -> '2 min 05 s', 3725 -> '1 h 02 min'."""
    seconds = max(0, round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"
