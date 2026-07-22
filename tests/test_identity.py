import json

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


def test_empty_token_rejected():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.hello("alfa", "i1", "")


def test_non_str_token_rejected():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.hello("alfa", "i1", 123)


def test_dump_restore_preserves_takeover():
    r = Registry(TOKENS)
    assert r.hello("alfa", "inst-1", "tok-a") == 1
    assert r.hello("alfa", "inst-2", "tok-a") == 2  # przejecie

    r2 = Registry.restore(TOKENS, r.dump())

    assert r2.hello("alfa", "inst-2", "tok-a") == 2  # reconnect, nie podbija
    assert r2.is_current("alfa", 2)
    assert not r2.is_current("alfa", 1)
    assert r2.hello("alfa", "inst-3", "tok-a") == 3  # kolejne przejecie


def test_empty_configured_token_fails_fast():
    with pytest.raises(ValueError):
        Registry({"alfa": ""})


def test_non_str_configured_token_fails_fast():
    with pytest.raises(ValueError):
        Registry({"alfa": 123})


def test_empty_nick_fails_fast():
    with pytest.raises(ValueError):
        Registry({"": "tok"})


def test_dump_contains_no_tokens():
    r = Registry({"alfa": "tajny-tok"})
    r.hello("alfa", "inst-1", "tajny-tok")
    d = r.dump()
    assert "tajny-tok" not in json.dumps(d)
    assert "tokens" not in d


def test_none_instance_id_rejected():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.hello("alfa", None, "tok-a")


def test_empty_instance_id_rejected():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.hello("alfa", "", "tok-a")


def test_non_str_nick_rejected():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.hello([], "i1", "tok-a")
    with pytest.raises(AuthError):
        r.hello({}, "i1", "tok-a")
    with pytest.raises(AuthError):
        r.hello("", "i1", "tok-a")


def test_external_token_map_mutation_has_no_effect():
    t = {"alfa": "tok"}
    r = Registry(t)
    t["intruz"] = "x"
    with pytest.raises(AuthError):
        r.hello("intruz", "i1", "x")


# -- H: role/grupy z configu serwera (decyzja tercetu) -----------------------

def test_old_flat_format_normalizes_to_agent_no_groups():
    r = Registry({"alfa": "tok-a"})
    assert r.role_of("alfa") == "agent"
    assert r.groups_of("alfa") == []
    assert r.hello("alfa", "i1", "tok-a") == 1  # konstruktor dalej dziala


def test_dict_format_configures_role_and_groups():
    r = Registry({
        "alfa": "tok-a",                                             # stary format
        "beta": {"token": "tok-b", "role": "human", "groups": ["ops", "admin"]},
    })
    assert r.role_of("beta") == "human"
    assert r.groups_of("beta") == ["ops", "admin"]
    assert r.hello("beta", "i1", "tok-b") == 1  # token dalej dziala


def test_dict_format_missing_token_fails_fast():
    with pytest.raises(ValueError):
        Registry({"alfa": {"role": "agent"}})


def test_dict_format_rejects_bad_role():
    with pytest.raises(ValueError):
        Registry({"alfa": {"token": "tok-a", "role": "superadmin"}})


def test_dict_format_rejects_non_list_groups():
    with pytest.raises(ValueError):
        Registry({"alfa": {"token": "tok-a", "groups": "not-a-list"}})


def test_dict_format_rejects_non_str_group_items():
    with pytest.raises(ValueError):
        Registry({"alfa": {"token": "tok-a", "groups": [123]}})


def test_bad_token_entry_shape_fails_fast():
    with pytest.raises(ValueError):
        Registry({"alfa": 123})  # ani str, ani dict
