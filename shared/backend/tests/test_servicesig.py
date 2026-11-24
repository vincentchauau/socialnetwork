import pytest

from sn_shared import servicesig

SECRET = "x" * 32
BODY = b'{"a":1}'
SCOPE = "POST /internal/ensure"


def headers(now=1000.0, secret=SECRET, body=BODY, scope=SCOPE):
    return servicesig.sign(secret, body, scope, now=now)


def check(h, body=BODY, secret=SECRET, now=1000.0, scope=SCOPE):
    return servicesig.verify(secret, body, scope, h[servicesig.TIMESTAMP_HEADER], h[servicesig.SIGNATURE_HEADER], now=now)


def test_a_fresh_signature_over_the_same_body_is_accepted():
    assert check(headers())


def test_a_changed_body_a_wrong_secret_or_a_forged_signature_is_refused():
    assert not check(headers(), body=b'{"a":2}')
    assert not check(headers(), secret="y" * 32)
    assert not servicesig.verify(SECRET, BODY, SCOPE, "1000", "0" * 64, now=1000.0)


def test_a_signature_is_good_only_for_the_call_it_was_made_for():
    assert not check(headers(), scope="DELETE /internal/rooms/ROOM1")
    assert not check(headers(body=b"", scope="DELETE /internal/rooms/ROOM1"), body=b"", scope="DELETE /internal/rooms/ROOM2")
    assert not check(headers(), scope="POST /internal/other")


def test_an_old_or_future_signature_is_refused():
    assert check(headers(now=1000.0), now=1000.0 + servicesig.MAX_SKEW_SECONDS)
    assert not check(headers(now=1000.0), now=1000.0 + servicesig.MAX_SKEW_SECONDS + 1)
    assert not check(headers(now=1000.0), now=1000.0 - servicesig.MAX_SKEW_SECONDS - 1)


def test_missing_parts_and_a_missing_secret_are_refused_not_crashed_on():
    assert not servicesig.verify(SECRET, BODY, SCOPE, None, "abc", now=1.0)
    assert not servicesig.verify(SECRET, BODY, SCOPE, "1", None, now=1.0)
    assert not servicesig.verify(SECRET, BODY, SCOPE, "not a number", "abc", now=1.0)
    assert not servicesig.verify("", BODY, SCOPE, "1000", "abc", now=1000.0)
    with pytest.raises(ValueError):
        servicesig.sign("short", BODY, SCOPE)
