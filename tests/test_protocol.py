import json
import pytest

from chat import protocol


def test_parse_mentions():
    assert protocol.parse_mentions("hej @alfa i @beta, reszta nie") == {"alfa", "beta"}
    assert protocol.parse_mentions("@all ruszamy") == {"all"}
    assert protocol.parse_mentions("bez wzmianek") == set()
    assert protocol.parse_mentions("mail x@y.z to nie wzmianka") == set()


def test_myslnik_nalezy_do_nicka_i_do_grupy():
    """Hub przyjmuje kazdy niepusty string jako nick, a rules kanalu pkt 15
    WPROST kaza prefiksowac nazwy pomocnicze wlasnym nickiem ("tester-worker3",
    "wt-worker2"). Przy samym \\w takie wzmianki rozpadaly sie CICHO:
    "@tester-worker3" dawalo "tester", ktorego nikt nie trzyma — adresat nie
    byl budzony, a nadawca nie dostawal bledu.

    Zmierzone na zywym kanale: 'tester-claude' wszedl poprawnie (hello
    seq 116), ramka "@tester-claude ..." trafila do logu (seq 118) i nie
    dotarla do niego wcale. Regula instruowala agentow, zeby brali nazwy,
    ktorych nikt nie moze zawolac."""
    assert protocol.parse_mentions("@tester-claude czesc") == {"tester-claude"}
    assert protocol.parse_mentions("@a-b-c x") == {"a-b-c"}
    assert protocol.parse_groups("$my-group x") == {"my-group"}
    # myslnik tylko MIEDZY segmentami — interpunkcja nie moze wejsc do nicka
    assert protocol.parse_mentions("@nick- koniec") == {"nick"}
    assert protocol.parse_mentions("@tester-claude, przecinek") == {"tester-claude"}
    # i nadal zaden adres e-mail nie jest wzmianka
    assert protocol.parse_mentions("pisz na a@nie-wzmianka.pl") == set()


def test_parse_groups():
    assert protocol.parse_groups("hej $workers i $review, reszta nie") == {"workers", "review"}
    assert protocol.parse_groups("bez grup") == set()
    assert protocol.parse_groups("cena5$workers to nie grupa") == set()
    assert protocol.parse_groups("") == set()


def test_make_frame_and_validate_ok():
    f = protocol.make_frame("chat", "alfa", ts=123.0, text="siema")
    assert f == {"type": "chat", "from": "alfa", "ts": 123.0, "text": "siema"}
    assert protocol.validate(f) is None


def test_validate_rejects():
    assert protocol.validate({"from": "x", "ts": 1.0}) == "missing type"
    assert protocol.validate({"type": "nope", "from": "x", "ts": 1.0}) == "unknown type: nope"
    assert protocol.validate({"type": "chat", "ts": 1.0}) == "missing from"
    assert protocol.validate({"type": "chat", "from": "x"}) == "missing ts"


# -- Runda 4 #5: schemat inbound per typ ramki -------------------------------

def test_validate_common_from_must_be_nonempty_string():
    assert protocol.validate({"type": "chat", "from": "", "ts": 1.0, "text": "x"})
    assert protocol.validate({"type": "chat", "from": 5, "ts": 1.0, "text": "x"})


def test_validate_common_ts_must_be_number_not_bool():
    assert protocol.validate({"type": "chat", "from": "a", "ts": "x", "text": "y"})
    assert protocol.validate({"type": "chat", "from": "a", "ts": True, "text": "y"})
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1, "text": "y"}) is None


def test_validate_fyi_requires_nonempty_text():
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0, "text": ""}) is not None
    assert protocol.validate({"type": "fyi", "from": "a", "ts": 1.0, "text": "hej"}) is None


def test_validate_status_requires_nonempty_string_state():
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0, "state": []}) is not None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0, "state": "idle"}) is None


def test_validate_status_state_is_free_text_up_to_32_chars():
    # (t4) hub nie waliduje przynaleznosci do enuma — dowolny wolny tekst
    # (niepusty, <=32 znaki) przechodzi; STATUS_STATES zostaje wylacznie
    # dokumentacja stanow umownych.
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "sleeping"}) is None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "cokolwiek-innego"}) is None
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "x" * 32}) is None            # brzeg OK
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": "x" * 33}) is not None        # za dlugie
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": ""}) is not None              # puste
    assert protocol.validate({"type": "status", "from": "a", "ts": 1.0,
                              "state": 5}) is not None                # nie-str


def test_validate_status_target_optional_but_nonempty_string_if_present():
    base = {"type": "status", "from": "a", "ts": 1.0, "state": "working"}
    assert protocol.validate(base) is None                            # brak target OK
    assert protocol.validate({**base, "target": "gamma"}) is None
    assert protocol.validate({**base, "target": ""}) is not None       # puste
    assert protocol.validate({**base, "target": 7}) is not None        # nie-str


def test_validate_status_subject_and_note_optional_nonempty_string():
    # B1: subject i note to opcjonalne pola statusu (niepusty string jesli
    # obecne). task_id ZRETIROWANE — subject je zastapil, board = {state,subject,note}.
    base = {"type": "status", "from": "a", "ts": 1.0, "state": "working"}
    assert protocol.validate({**base, "subject": "audyt logu"}) is None
    assert protocol.validate({**base, "note": "czekam"}) is None
    assert protocol.validate({**base, "subject": "s", "note": "n"}) is None
    assert protocol.validate({**base, "subject": ""}) is not None       # puste
    assert protocol.validate({**base, "subject": []}) is not None       # nie-str
    assert protocol.validate({**base, "note": ""}) is not None
    # task_id ZRETIROWANE — validate ODRZUCA je jawnie (nie ciche unknown),
    # zeby handler _append/broadcast nie utrwalil go do logu/live zanim
    # board-projekcja by je odsiala. Sam drop na boardzie nie wystarcza.
    assert protocol.validate({**base, "task_id": "legacy"}) is not None


def test_validate_membership_set_requires_target_and_group_list():
    base = {"type": "membership_set", "from": "emil", "ts": 1.0}
    assert protocol.validate({**base, "target": "beta", "groups": []}) is None
    assert protocol.validate({**base, "target": "beta",
                              "groups": ["head", "admin"]}) is None
    assert protocol.validate({**base, "target": "", "groups": []}) is not None
    assert protocol.validate({**base, "target": "beta", "groups": "admin"}) is not None
    assert protocol.validate({**base, "target": "beta", "groups": [""]}) is not None


def test_validate_inbound_task_and_heartbeat_now_unknown():
    # laka-nie-obora (A2/A3): inbound task_*/heartbeat WYCIETE — dawne typy
    # zlecen taskowych sa teraz NIEZNANE, klient nie moze ich przyslac.
    for ftype in ("task_new", "task_claim", "task_done", "task_blocked",
                  "review_changes", "task_approve", "task_unblock", "heartbeat"):
        assert protocol.validate({"type": ftype, "from": "a", "ts": 1.0}) == \
            f"unknown type: {ftype}"


def test_validate_rejects_outbound_only_types_inbound_but_known():
    for ftype in ("backlog", "resync_required", "error", "ok",
                  "presence", "takeover"):
        msg = protocol.validate({"type": ftype, "from": "a", "ts": 1.0})
        assert msg is not None                    # odrzucone inbound-em
        assert "unknown type" not in msg          # ale to ZNANE typy (nie nieznane)


# -- Runda 5: walidacja inbound pelna (type nie-str, ts skonczone) ----------

def test_validate_nonstring_type_does_not_raise_unhashable():
    # (C1) type=[] / {} to unhashable — membership `in FRAME_TYPES` PRZED
    # sprawdzeniem ze type to str rzucalo TypeError. Musi zwrocic error, nie rzucic.
    assert protocol.validate({"type": [], "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": {}, "from": "a", "ts": 1.0}) is not None
    assert protocol.validate({"type": "", "from": "a", "ts": 1.0}) is not None
    # znany zly typ (str) nadal daje czytelne "unknown type: ..."
    assert protocol.validate({"type": "nope", "from": "a", "ts": 1.0}) == "unknown type: nope"


def test_validate_ts_must_be_finite():
    # (C2) NaN/inf przechodzily (validate=None) -> logowany niestandardowy JSON
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("nan"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("inf"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": float("-inf"),
                              "text": "x"}) is not None
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1.5,
                              "text": "x"}) is None


def test_validate_huge_int_ts_rejected_no_overflow():
    # (Runda 6 #3) math.isfinite(10**400) rzuca OverflowError (legalny JSON int
    # za duzy na float) — wysypywalo CALA walidacje zamiast zwrocic blad. int
    # poza zakresem float odrzucony KOMUNIKATEM (bez OverflowError); normalny
    # int ts nadal przechodzi (isfinite wolane tylko dla float).
    frame = {"type": "chat", "from": "a", "ts": 10**400, "text": "x"}
    msg = protocol.validate(frame)                 # NIE moze rzucic OverflowError
    assert isinstance(msg, str) and msg            # ramka odrzucona komunikatem
    assert protocol.validate({"type": "chat", "from": "a", "ts": 1,
                              "text": "x"}) is None  # zwykly int nadal ok


@pytest.mark.parametrize("baza", [
    {"type": "hello", "from": "alfa", "ts": 0.0,
     "instance_id": "i1", "last_seq": 0},
    # B6: hello w trybie otwartym NIE niesie nicka. To wlasnie ta sciezka
    # jest tu najwazniejsza — agent wpuszczany po niezalezna perspektywe
    # czesto nie ma jeszcze wlasnego nicka i prosi hub o dowolny wolny.
    {"type": "hello", "ts": 0.0, "instance_id": "i1", "last_seq": 0},
])
def test_hello_context_fail_closed_takze_bez_nicka(baza):
    """Fail-closed: nieznany tryb wejscia to blad, nie ciche 'full'.
    Ciche zignorowanie znaczyloby, ze agent proszacy o wejscie bez kotwicy
    dostaje cala rozmowe i nigdy sie o tym nie dowie."""
    assert protocol.validate({**baza, "context": "fresh"}) is None
    assert protocol.validate({**baza, "context": "full"}) is None
    assert protocol.validate(baza) is None                    # brak = full
    assert protocol.validate({**baza, "context": "bare"}) is not None
    assert protocol.validate({**baza, "context": 1}) is not None


# --- clamp_frame: log sprzed sufitu wejscia -------------------------------

def test_clamp_nie_rusza_ramki_ktora_sie_miesci():
    ramka = {"type": "chat", "from": "a", "ts": 0.0, "seq": 7, "text": "krotko"}
    assert protocol.clamp_frame(ramka) is ramka


def test_clamp_przycina_stara_wielka_ramke_zachowujac_tozsamosc():
    """Sufit wejscia nie przepisuje historii: log sprzed niego moze trzymac
    ramki blisko 1 MiB, a 51 takich w oknie rozmowy przekracza sufit odbioru
    klienta — wznowienie pada po UPGRADZIE huba (szoste review Codexa).

    Przycinamy `text`, a NIE pomijamy ramki: seq/from/type zostaja, wiec
    kursor liczy sie tak samo i nic nie znika po cichu."""
    tekst = "A" * (protocol.MAX_FRAME_BYTES * 2)
    ramka = {"type": "chat", "from": "stary", "ts": 1.0, "seq": 42, "text": tekst}
    out = protocol.clamp_frame(ramka)

    assert protocol.frame_bytes(out) <= protocol.MAX_FRAME_BYTES
    assert (out["seq"], out["from"], out["type"]) == (42, "stary", "chat")
    assert out["truncated"] == len(tekst), "brak prawdziwej dlugosci oryginalu"
    assert out["text"].endswith(protocol.TRUNCATION_MARK)
    assert ramka["text"] == tekst, "clamp zmutowal ramke z logu"


def test_clamp_nie_lamie_znaku_wielobajtowego():
    """Ciecie idzie po BAJTACH (tak liczy max_size), wiec musi domknac
    rozciety znak — inaczej na drut szedlby polamany UTF-8."""
    ramka = {"type": "chat", "from": "a", "ts": 0.0, "seq": 1,
             "text": "😀" * protocol.MAX_FRAME_BYTES}
    out = protocol.clamp_frame(ramka)
    assert protocol.frame_bytes(out) <= protocol.MAX_FRAME_BYTES
    out["text"].encode("utf-8").decode("utf-8")     # nie rzuca = znak domkniety
    assert "�" not in out["text"]


def test_clamp_oddaje_ramke_bez_tekstu_bez_zmian():
    """Nie ma czego przyciac (np. wielki snapshot w innym polu) — oddajemy
    jak jest zamiast udawac, ze zmiescilismy."""
    ramka = {"type": "status", "from": "a", "ts": 0.0, "seq": 1,
             "note": "B" * (protocol.MAX_FRAME_BYTES * 2)}
    assert protocol.clamp_frame(ramka) is ramka


@pytest.mark.parametrize("nazwa,znak", [
    ("nul", "\x00"),            # 1 bajt rosnie do szesciu: 
    ("cudzyslow", '"'),         # do dwoch
    ("backslash", "\\"),
    ("nowa_linia", "\n"),
    ("tab", "\t"),
    ("emoji", "\U0001F600"),
    ("zwykly", "A"),
    ("mieszanka", 'a"\x00\U0001F600\n'),
])
def test_clamp_dowozi_sufit_takze_dla_znakow_escapowanych(nazwa, znak):
    """Miara to `frame_bytes` GOTOWEJ ramki, nie dlugosc prefiksu tekstu.

    Pierwsza wersja ciela po surowych bajtach UTF-8 i obiecywala sufit,
    ktorego nie dowozila — `dumps` escapuje znaki sterujace, wiec NUL rosnie
    z 1 bajtu do szesciu. Zmierzone na PRZYCIETEJ ramce: NUL 392 KiB,
    cudzyslow 131 KiB przy sufitcie 64 KiB (siodme review Codexa).
    200 takich ramek znow przekraczalo sufit klienta i blokowalo wznowienie."""
    ramka = {"type": "chat", "from": "a", "ts": 0.0, "seq": 1,
             "text": znak * 100000}
    out = protocol.clamp_frame(ramka)
    assert protocol.frame_bytes(out) <= protocol.MAX_FRAME_BYTES, nazwa
    assert out["truncated"] == 100000 * len(znak)
    assert json.loads(protocol.dumps(out))["text"] == out["text"]


def test_clamp_zostawia_ile_sie_da_a_nie_stala_reszte():
    """Przyciecie ma byc NAJDLUZSZYM prefiksem, ktory wchodzi — inaczej agent
    placi kontekstem za ostroznosc implementacji. Tekst bez escapowania musi
    zmiescic wielokrotnie wiecej znakow niz tekst z samych NUL-i."""
    def zachowane(znak):
        ramka = {"type": "chat", "from": "a", "ts": 0.0, "seq": 1,
                 "text": znak * 100000}
        return len(protocol.clamp_frame(ramka)["text"])

    assert zachowane("A") > 60000
    assert zachowane("A") > 5 * zachowane("\x00")
