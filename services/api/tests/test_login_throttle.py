"""Sign-in attempts per address are limited before the password check (routers/auth.throttled)."""
from sentinel_api.routers.auth import LOGIN_PER_MINUTE, _attempts, throttled


def test_the_limit_applies_per_address_per_minute():
    _attempts.clear()
    t = 1000.0
    for i in range(LOGIN_PER_MINUTE):
        assert not throttled("10.0.0.9", t + i)          # the first 30 in a minute go through
    assert throttled("10.0.0.9", t + 40)                  # the 31st does not
    assert not throttled("10.0.0.10", t + 40)             # another address is unaffected
    assert not throttled("10.0.0.9", t + 61)              # a minute after the first, room again
