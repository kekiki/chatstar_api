import pytest

from app.online_status import get_online_status


@pytest.mark.parametrize(
    ("has_live_media", "fans_count", "expected"),
    [
        (False, 0, 1),
        (False, 1, 1),
        (True, 1, 0),
        (True, 2, 2),
        (True, None, 2),
    ],
)
def test_get_online_status(has_live_media, fans_count, expected):
    assert get_online_status(has_live_media, fans_count) == expected
