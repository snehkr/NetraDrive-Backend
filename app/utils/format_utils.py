# app/utils/format_utils.py


# Format bytes
def format_bytes(size: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


# Format estimated time
def format_eta(seconds: float | None) -> str:
    """Convert seconds to friendly string like '1h 3m 5s'."""
    if seconds is None:
        return "N/A"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, sec = divmod(remainder, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return " ".join(parts)
