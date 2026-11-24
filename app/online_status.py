"""Shared online status mapping for user-facing API responses."""


def get_online_status(has_live_media: bool, fans_count: int | None) -> int:
    """Return 2 for live, 0 for non-live media users, otherwise 1."""
    if not has_live_media:
        return 1
    return 2 if (fans_count or 0) % 2 == 0 else 0
