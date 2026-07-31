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
    assert r.generation_of("alfa") == g1


def test_takeover_bumps_generation_and_invalidates_old():
    r = Registry(TOKENS)
    g1 = r.hello("alfa", "inst-1", "tok-a")
    g2 = r.hello("alfa", "inst-2", "tok-a")  # przejecie nicku
    assert g2 == g1 + 1
    assert r.generation_of("alfa") == g2


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
    assert r2.generation_of("alfa") == 2
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


def test_groups_can_change_without_changing_stable_role_and_survive_snapshot():
    tokens = {
        "beta": {"token": "tb", "role": "agent", "groups": ["workers"]},
        "emil": {"token": "te", "role": "human", "groups": []},
    }
    registry = Registry(tokens)
    assert registry.set_groups("beta", ["head", "admin", "admin"]) == [
        "head", "admin"]
    assert registry.role_of("beta") == "agent"

    restored = Registry.restore(tokens, registry.dump())
    assert restored.groups_of("beta") == ["head", "admin"]
    assert restored.role_of("beta") == "agent"


def test_set_groups_rejects_unknown_target_and_bad_groups():
    registry = Registry(TOKENS)
    with pytest.raises(AuthError):
        registry.set_groups("unknown", ["admin"])
    with pytest.raises(AuthError):
        registry.set_groups("beta", [""])


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


# -- A: replay_hello (crash-recovery) — bump generacji bez tokenu -----------

def test_replay_hello_bumps_generation_like_hello_without_token():
    r = Registry(TOKENS)
    assert r.replay_hello("alfa", "inst-1") == 1
    assert r.replay_hello("alfa", "inst-1") == 1        # ten sam instance — bez bumpa
    assert r.replay_hello("alfa", "inst-2") == 2        # inny instance — bump
    assert r.generation_of("alfa") == 2


def test_replay_hello_matches_live_hello_sequence():
    live = Registry(TOKENS)
    g1 = live.hello("alfa", "i1", "tok-a")
    g2 = live.hello("alfa", "i2", "tok-a")

    replayed = Registry(TOKENS)   # symulacja: log ma tylko hello (bez tokenu)
    r1 = replayed.replay_hello("alfa", "i1")
    r2 = replayed.replay_hello("alfa", "i2")
    assert (r1, r2) == (g1, g2)


def test_replay_hello_rejects_invalid_nick_or_instance():
    r = Registry(TOKENS)
    with pytest.raises(AuthError):
        r.replay_hello("", "i1")
    with pytest.raises(AuthError):
        r.replay_hello("alfa", "")
    with pytest.raises(AuthError):
        r.replay_hello("alfa", None)


# --- B6: wejscie bez tokenu (tryb otwarty) ------------------------------
# Tozsamosc opiera sie na sieci (tailnet) i moderacji czlowieka, nie na
# sekrecie do przepisania. Token zostaje wylacznie dla roli human.

def test_open_hello_admits_unknown_nick_with_default_role_and_groups():
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    gen = reg.open_hello("nowy-agent", "i1")
    assert gen == 1
    assert reg.role_of("nowy-agent") == "agent"
    assert reg.groups_of("nowy-agent") == [], \
        "bez grupy agent jest technicznie na kanale i praktycznie gluchy"


def test_open_hello_refuses_to_impersonate_human():
    """Rola human wymaga tokenu ZAWSZE — inaczej dowolny uczestnik tailnetu
    wszedlby jako moderator i wyrzucal pozostalych."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    with pytest.raises(AuthError):
        reg.open_hello("emil", "i1")


def test_open_hello_keeps_config_role_for_known_agent():
    """Nick z tokens.json zachowuje swoje grupy takze przy wejsciu otwartym."""
    reg = Registry({"beta": {"token": "tb", "role": "agent",
                             "groups": ["workers", "reviewers"]}})
    reg.open_hello("beta", "i1")
    assert sorted(reg.groups_of("beta")) == ["reviewers", "workers"]


# --- B7: nick przypiety do adresu (tryb open) ------------------------------

def test_open_hello_binds_nick_to_first_address():
    """Pierwsze wejscie zapamietuje adres; ten sam adres przechodzi."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    reg.open_hello("agent", "i1", addr="100.64.0.5")
    # ten sam adres, kolejny instance (reconnect/self) — przechodzi
    reg.open_hello("agent", "i2", addr="100.64.0.5")
    assert reg.instance_of("agent") == "i2"


def test_open_hello_refuses_other_address_on_bound_nick():
    """Podszycie: inny adres na przypiety nick = odmowa (rdzen B7)."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    reg.open_hello("ofiara", "i1", addr="100.64.0.5")
    with pytest.raises(AuthError):
        reg.open_hello("ofiara", "PODSZYWACZ", addr="100.64.0.9")


def test_open_hello_address_beats_instance_id():
    """instance_id jest PUBLICZNY (trafia do logu), wiec NIE moze przelamac
    wiazania — inny adres = odmowa nawet z tym samym instance. Inaczej
    podszywacz ze skradzionym instance z innego adresu przejmuje nick."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    reg.open_hello("agent", "i1", addr="100.64.0.5")
    with pytest.raises(AuthError):
        reg.open_hello("agent", "i1", addr="100.64.0.9")  # ten sam instance!


def test_open_hello_no_addr_does_not_bind():
    """addr=None (bind loopback: IP nie rozroznia) — brak wiazania, dowolne
    kolejne wejscia przechodza."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    reg.open_hello("agent", "i1", addr=None)
    reg.open_hello("agent", "i2", addr=None)   # bez wyjatku
    assert reg.instance_of("agent") == "i2"


def test_release_open_addr_frees_binding():
    """kick zwalnia wiazanie: po release inny adres wchodzi (re-IP / nowy
    wlasciciel nicka po rozkazie roota)."""
    reg = Registry({"emil": {"token": "te", "role": "human", "groups": []}})
    reg.open_hello("agent", "i1", addr="100.64.0.5")
    reg.release_open_addr("agent")
    reg.open_hello("agent", "i2", addr="100.64.0.9")   # bez wyjatku
    assert reg.instance_of("agent") == "i2"


def test_nieznany_agent_nie_dostaje_domyslnej_grupy():
    """PAKIET 0 (plan V1): grupa to ADRES, ktory ktos swiadomie nadal —
    nie klasa, do ktorej hub zapisuje kazdego wchodzacego.

    Dotychczas nieznany nick dostawal `workers` z uzasadnieniem, ze inaczej
    bedzie gluchy na `$workers`. To rozumowanie jest zamkniete w kolo:
    grupa jest potrzebna tylko dlatego, ze hub sam ja wszystkim nadaje.
    Gdy nikt nie ma domyslnej grupy, nikt nie wola `$workers` i problem
    znika — a mechanizm grup zostaje dla operatora, ktory chce go uzyc.

    Konstytucja: "nie kodujemy ludzkich zalozen o organizacji (...) ani
    sposobie podzialu obowiazkow"."""
    reg = Registry({"human": {"token": "th", "role": "human", "groups": []}})
    reg.open_hello("ktos-nowy", "inst-1", None)
    assert reg.groups_of("ktos-nowy") == [], \
        "hub zapisuje wchodzacego do klasy, ktorej nikt nie zadeklarowal"
    assert reg.role_of("ktos-nowy") == "agent"


def test_agent_z_trybu_otwartego_zachowuje_admina_po_restarcie():
    """Odkad swiezy pokoj ma w tokens.json sam `human`, KAZDY agent wchodzi
    bez tokenu — a `restore()` odtwarzalo grupy wylacznie dla nickow z pliku.
    Skutek: `admin` nadany przez membership_set znikal przy pierwszym
    restarcie huba, razem z cala rola. Jedyna droga do uprawnien konczyla sie
    wiec na pierwszym `stop`/`serve`.

    Snapshot ma po takim nicku dokladnie jeden slad — wpis w `gen`. To on
    wystarcza, zeby go odtworzyc: rola moze byc tylko "agent", bo open_hello
    odmawia wejscia na konto human (zlapane 2026-07-31, review Codexa)."""
    tokens = {"human": {"token": "th", "role": "human", "groups": []}}
    registry = Registry(tokens)
    registry.open_hello("agent1", "inst-1", None)
    registry.set_groups("agent1", ["admin"])

    restored = Registry.restore(tokens, registry.dump())
    assert restored.role_of("agent1") == "agent"
    assert restored.groups_of("agent1") == ["admin"], \
        "restart odbiera agentowi z trybu otwartego grupy nadane przez admina"
    # tozsamosc ma byc ZNANA, inaczej membership_set odbija sie od niej
    restored.set_groups("agent1", ["admin", "head"])


def test_restore_nie_nadaje_roli_human_nickowi_spoza_tokenow():
    """Odtwarzanie tozsamosci z `gen` nie moze byc furtka do moderacji:
    rola human pochodzi WYLACZNIE z tokens.json. Gdyby nick wykreslony
    z pliku wracal jako human, edycja pliku sekretow przestalaby cokolwiek
    odbierac."""
    tokens = {"human": {"token": "th", "role": "human", "groups": []},
              "bylec": {"token": "tb", "role": "human", "groups": ["admin"]}}
    registry = Registry(tokens)
    registry.hello("bylec", "inst-1", "tb")
    snapshot = registry.dump()

    bez_bylca = {"human": {"token": "th", "role": "human", "groups": []}}
    restored = Registry.restore(bez_bylca, snapshot)
    assert restored.role_of("bylec") == "agent", \
        "nick wykreslony z tokens.json wraca z rola moderatora"


def test_replay_hello_odtwarza_tozsamosc_z_trybu_otwartego():
    """Agent, ktory wszedl PO ostatnim snapshocie, istnieje tylko w logu.
    Bez odtworzenia roli w replay_hello wypadal z `roles` po restarcie —
    a wtedy membership_set odbijalo sie od niego jako "unknown target"
    i lustro ChatServer.groups go nie widzialo."""
    registry = Registry({"human": {"token": "th", "role": "human", "groups": []}})
    registry.replay_hello("agent7", "inst-7")
    assert registry.role_of("agent7") == "agent"
    assert registry.groups_of("agent7") == []
    assert registry.set_groups("agent7", ["admin"]) == ["admin"]


def test_replay_hello_nie_kasuje_grup_odtworzonych_ze_snapshotu():
    """Kolejnosc bootu to snapshot -> replay logu. Gdyby replay_hello
    zerowal grupy przy KAZDYM hello, reconnect zapisany po membership_set
    kasowalby wlasnie odtworzone czlonkostwo."""
    tokens = {"human": {"token": "th", "role": "human", "groups": []}}
    registry = Registry(tokens)
    registry.open_hello("agent1", "inst-1", None)
    registry.set_groups("agent1", ["admin"])
    restored = Registry.restore(tokens, registry.dump())

    restored.replay_hello("agent1", "inst-2")   # reconnect z ogona logu
    assert restored.groups_of("agent1") == ["admin"], \
        "replay reconnectu kasuje czlonkostwo odtworzone ze snapshotu"
