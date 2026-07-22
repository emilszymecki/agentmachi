import pytest
from chat.identity import Registry, AuthError

TOKENS = {"alfa": "tok-a", "beta": "tok-b"}


def test_hello_issues_generation_and_auth():
    r = Registry(TOKENS)
    assert r.hello("alfa", "inst-1", "tok-a") == 1
    with pytest.raises(AuthError):
        r.hello("alfa", "inst-1", "zly-token")
    with pytest.raises(AuthError):
        r.hello("nieznany", "inst-1", "cokolwiek")


def test_reconnect_same_instance_keeps_generation():
    r = Registry(TOKENS)
    g1 = r.hello("alfa", "inst-1", "tok-a")
    g2 = r.hello("alfa", "inst-1", "tok-a")  # reconnect / drugi socket
    assert g1 == g2 == 1
    assert r.is_current("alfa", g1)


def test_takeover_bumps_generation_and_invalidates_old():
    r = Registry(TOKENS)
    g1 = r.hello("alfa", "inst-1", "tok-a")
    g2 = r.hello("alfa", "inst-2", "tok-a")  # przejecie nicku
    assert g2 == g1 + 1
    assert not r.is_current("alfa", g1)
    assert r.is_current("alfa", g2)


def test_unknown_nick_with_none_token_rejected():
    r = Registry({"alfa": "tok-a"})
    with pytest.raises(AuthError):
        r.hello("unknown", "i1", None)  # None != None auth-bypass
    with pytest.raises(AuthError):
        r.hello("alfa", "i1", None)  # znany nick, brak tokenu tez odrzucony
