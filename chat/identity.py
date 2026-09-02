"""Tozsamosc logiczna: nick + instance_id -> generation. Token per agent.

Tokens map (decyzja tercetu, H): kazda wartosc to albo string (STARY
format, kompatybilnosc — normalizowany do role="agent", groups=[]),
albo dict {"token": str, "role": "agent"|"human", "groups": [str, ...]}.
role jest stala KONFIGURACJA SERWERA. groups startuja z konfiguracji, ale
moga byc pozniej zmieniane przez trwaly event membership_set. To co agent
deklaruje we wlasnym hello jest tylko walidowane i nigdy nie nadpisuje
przypisania serwera (patrz server.py).
"""

import hmac
import unicodedata

_VALID_ROLES = ("agent", "human")

# Kategorie Unicode, ktorych nick miec NIE MOZE. Lista jest po WLASNOSCI,
# nie po znakach, i to jest cala jej tresc:
#
#   Cc  sterujace (\n, \r, \x1b — ANSI przepisuje juz wydrukowany wiersz),
#   Cf  formatujace (RLO/LRO odwracaja kolejnosc, ZWSP/BOM znikaja bez sladu),
#   Cs  surogaty, Co prywatne, Cn nieprzypisane — renderuja sie roznie
#       w kazdym terminalu, wiec nick nie jest tym samym napisem u dwoch osob,
#   Zl/Zp/Zs  separatory linii, akapitu i spacje — `@nick` konczy sie na
#       bialym znaku, wiec nick ze spacja jest NIEADRESOWALNY.
#
# Czarnej listy KONKRETNYCH znakow tu nie ma i nie bedzie: zakaz znaku
# utrwala go jako specjalny i przegrywa z pierwszym znakiem, o ktorym autor
# listy nie pomyslal. Mysnik, podkreslnik i litery spoza ASCII (`ł`, `é`,
# `日`) przechodza — sa dozwolone celowo i test falsyfikuje to w obie strony.
_ZLE_KATEGORIE = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs"})


def sprawdz_ksztalt_nicka(nick):
    """Podnies AuthError, gdy nick nie jest ADRESOWALNA tozsamoscia.

    Dziura z red-teamu (`redteam-batch-2026-09-01.md`, dziura 2): hub
    przyjmowal nick ze znakami kontrolnymi, bo jedynym warunkiem bylo
    „niepusty string". Skutek siega dalej niz kosmetyka renderu: nick jest
    JEDYNYM sposobem zaadresowania uczestnika (`@nick`), a `board` i TUI
    ustawiaja go w kolumnach. Nick niosacy `\\n` albo RLO nie jest tozsamoscia
    — jest sposobem na to, zeby wygladac na kogos innego w kazdym miejscu,
    ktore te kolumny drukuje.

    Sprawdzamy WLASNOSC („czy da sie to zaadresowac i czy wyglada tak samo
    u wszystkich"), nie liste znakow — patrz `_ZLE_KATEGORIE`."""
    for znak in nick:
        if unicodedata.category(znak) in _ZLE_KATEGORIE:
            # Znak podajemy jako codepoint, nie doslownie: gdybysmy wkleili
            # go do komunikatu, ten sam RLO/ANSI przepisalby TEN wydruk.
            raise AuthError(
                f"nick contains a character that cannot be addressed or "
                f"rendered the same way everywhere: U+{ord(znak):04X} "
                f"(category {unicodedata.category(znak)})")

# Wiazanie, ktorego NIE DA SIE dopasowac do zadnego adresu peera. Uzywane
# wylacznie przez replay logu SPRZED pola `open_addr` w evencie hello: gdy
# w ogonie logu byl `kick` (kasuje wiazanie), a po nim ponowne wejscie
# (stary format, adresu nie niesie), rejestr nie ma jak odtworzyc, do czego
# nick byl przypiety. Zostawienie go NIEZWIAZANYM oddaje go pierwszemu
# chetnemu z tailnetu — wiec zamiast tego wiazemy go z niczym: wlasciciel
# tez sie odbije, ale dostanie komunikat z gotowa droga wyjscia (moderator
# robi `kick`, ktory zwalnia wiazanie na dobre). Fail-closed zamiast
# zgadywania tozsamosci.
UNRESOLVED_ADDR = "\x00nieodtworzone-wiazanie"

# Nick, ktorym podpisuje sie sam hub (`protocol.make_frame(..., "server", ...)`)
# — zarezerwowany w OBU sciezkach wejscia. `from` jest polem autorytatywnym:
# klient je przysyla, ale prawda jest wylacznie to, co wpisze serwer. Nick
# `server` obchodzil ten inwariant nie przez podrobienie pola, tylko przez
# zajecie NAZWY: ramka takiego uczestnika ma `from: "server"` zgodnie z prawda
# i w renderze czytelnym (`[seq] server: tresc`) nie da sie jej odroznic od
# ramki huba. Zlapane 2026-08-13 na pokoju `poligon` przy recenzji cudzej
# poprawki i potwierdzone WEJSCIEM: hub wpuscil takiego uczestnika i pokazal
# go na boardzie.
#
# Rola `human` byla chroniona od poczatku, bo podszycie sie pod moderatora
# widziano jako ryzyko. Podszycie sie pod serwer przeoczono, choc jest
# mocniejsze: moderator moze wyrzucic, a serwer mowi, KTO zostal wyrzucony.
#
# Odtwarzania z logu to NIE dotyczy: pokoj, ktory takiego uczestnika juz ma,
# musi dac sie wznowic. Trwalosc bije czystosc rejestru.
NICK_SERWERA = "server"


class AuthError(Exception):
    pass


class Registry:
    def __init__(self, tokens):
        self.tokens = {}   # nick -> token
        self.roles = {}    # nick -> "agent"|"human" (konfiguracja serwera)
        self.groups = {}   # nick -> list[str] (konfiguracja serwera)
        for nick, entry in tokens.items():
            if not isinstance(nick, str) or not nick:
                raise ValueError(f"bad nick in tokens map: {nick!r}")
            if isinstance(entry, str):
                token, role, groups = entry, "agent", []
            elif isinstance(entry, dict):
                token = entry.get("token")
                role = entry.get("role", "agent")
                groups = entry.get("groups", [])
            else:
                raise ValueError(f"bad token entry for nick {nick!r}: {entry!r}")
            if not isinstance(token, str) or not token:
                raise ValueError(f"bad token for nick {nick!r}: {token!r}")
            if role not in _VALID_ROLES:
                raise ValueError(f"bad role for nick {nick!r}: {role!r}")
            if not isinstance(groups, list) or not all(
                    isinstance(g, str) and g for g in groups):
                raise ValueError(f"bad groups for nick {nick!r}: {groups!r}")
            self.tokens[nick] = token
            self.roles[nick] = role
            self.groups[nick] = list(groups)
        self._gen = {}                # nick -> int
        self._instance = {}           # nick -> aktualny instance_id
        self._open_addr = {}          # nick -> host (B7: wiazanie w trybie open)

    def role_of(self, nick):
        return self.roles.get(nick, "agent")

    def groups_of(self, nick):
        return self.groups.get(nick, [])

    def set_groups(self, nick, groups):
        """Ustaw plynna funkcje operacyjna; role agent/human pozostaje stala."""
        # Znana tozsamosc to `roles`, NIE `tokens`. `roles` jest nadzbiorem:
        # dostaje wpis dla kazdego posiadacza tokenu (__init__) ORAZ dla
        # kazdego, kto wszedl w trybie otwartym (open_hello). Sprawdzanie
        # `tokens` znaczylo, ze grupy dawalo sie nadac wylacznie posiadaczom
        # sekretu — a odkad swiezy pokoj ma w tokens.json sam `human`,
        # NIKOMU. `admin` nadaje sie wylacznie ta droga, wiec jedyne
        # przejscie do uprawnien bylo zamkniete (zlapane 2026-07-31).
        if not isinstance(nick, str) or not nick or nick not in self.roles:
            raise AuthError(f"unknown target: {nick!r}")
        if not isinstance(groups, list) or not all(
                isinstance(group, str) and group for group in groups):
            raise AuthError(f"invalid groups: {groups!r}")
        normalized = list(dict.fromkeys(groups))
        self.groups[nick] = normalized
        return list(normalized)

    def hello(self, nick, instance_id, token):
        if not isinstance(nick, str) or not nick:
            raise AuthError("invalid nick")
        if nick == NICK_SERWERA:
            raise AuthError(f"{NICK_SERWERA!r} is reserved for the hub itself")
        if nick not in self.tokens:
            raise AuthError(f"bad token for {nick}")
        expected = self.tokens[nick]
        if not isinstance(token, str) or not token:
            raise AuthError(f"bad token for {nick}")
        if not hmac.compare_digest(expected, token):
            raise AuthError(f"bad token for {nick}")
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        return self._bump(nick, instance_id)

    def open_hello(self, nick, instance_id, addr=None):
        """B6: wejscie BEZ tokenu (tryb otwarty — patrz ChatServer.open_mode).

        Tozsamosc opiera sie na sieci i moderacji czlowieka, nie na sekrecie:
        do huba dosiegnie tylko maszyna z tailnetu, a moderator widzi kazde
        wejscie i moze je odwolac (`kick`). Token zostaje wylacznie dla roli
        human — bez tego dowolny uczestnik tailnetu wszedlby jako moderator
        i wyrzucal pozostalych.

        Nick nieznany dostaje role agenta i ZADNEJ grupy. Wczesniej hub
        wpisywal go do `workers` z obawy, ze inaczej bedzie gluchy na
        wzmianki grupowe — ale to rozumowanie bylo zamkniete w kolo: grupa
        byla potrzebna wylacznie dlatego, ze hub sam ja wszystkim nadawal.
        Gdy nikt nie ma domyslnej grupy, nikt nie wola `$workers`. Grupy
        zostaja jako mechanizm adresowania, ktory nadaje czlowiek albo
        `admin` (membership_set) — swiadomie, a nie z automatu.

        Nick znany z tokens.json zachowuje swoja konfiguracje (grupy
        z pliku), tylko nie musi dowodzic tokenem.
        """
        if not isinstance(nick, str) or not nick:
            raise AuthError("invalid nick")
        if nick == NICK_SERWERA:
            raise AuthError(f"{NICK_SERWERA!r} is reserved for the hub itself")
        # Tylko TA sciezka: w trybie otwartym nick pochodzi WPROST od
        # wchodzacego, wiec jest wejsciem od klienta i podlega kontraktowi
        # wejscia. Sciezka tokenowa bierze nick z `tokens.json`, ktory pisze
        # operator na wlasnej maszynie — tam kontrola nie broni przed
        # napastnikiem, tylko potrafi zamknac dzialajacy pokoj przy starcie.
        # Granica jest swiadoma, nie przeoczona.
        sprawdz_ksztalt_nicka(nick)
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        if self.roles.get(nick) == "human":
            raise AuthError(
                f"{nick} is a moderator account — entry requires a token")
        # B7: wiazanie nick->adres. `addr` przekazuje serwer TYLKO wtedy, gdy
        # IP-binding jest aktywny (bind na interfejsie tailnetu — patrz
        # server _bind_is_tailnet); None znaczy "nie wiaz" (bind loopback:
        # lokalny test, adres nie rozroznia podmiotow). Host-check jest BRAMA
        # PRZED instance-check: `instance_id` jest publiczny (trafia do logu),
        # wiec NIE moze przelamac wiazania — inaczej podszywacz ze skradzionym
        # instance z INNEGO adresu przejalby nick. Inny adres = odmowa,
        # niezaleznie od instance_id; legalna zmiana adresu (re-IP) idzie przez
        # human `kick`, ktory zwalnia wiazanie (release_open_addr).
        if addr is not None:
            bound = self._open_addr.get(nick)
            if bound is not None and bound != addr:
                raise AuthError(
                    f"nick {nick} is pinned to a different address; pick "
                    f"another nick or ask a moderator to release it (kick)")
        if nick not in self.roles:
            # PAKIET 1: BEZ domyslnej grupy. Grupa to adres, ktory ktos
            # swiadomie nadal — nie klasa, do ktorej hub zapisuje kazdego
            # wchodzacego. Dawne uzasadnienie ("bez grupy bedzie gluchy na
            # $workers") jest zamkniete w kolo: grupa byla potrzebna tylko
            # dlatego, ze hub sam ja wszystkim nadawal. Gdy nikt nie ma
            # domyslnej grupy, nikt nie wola $workers i problem znika.
            # Mechanizm grup zostaje dla operatora (membership_set).
            self.roles[nick] = "agent"
            self.groups[nick] = []
        gen = self._bump(nick, instance_id)
        # Zapis PO udanym bump, na tej samej instancji (na klonie w serwerze —
        # provisional-then-commit: commit razem z registry swap po durable
        # append hello, jak generation/instance).
        if addr is not None:
            self._open_addr[nick] = addr
        return gen

    def release_open_addr(self, nick):
        """B7: zwolnij wiazanie nick->adres (rozkaz roota bije wiazanie).

        Wolane przy kick: moderator wyrzuca uczestnika i zwalnia jego
        tozsamosc, zeby ktos inny — albo ten sam agent z NOWEGO adresu po
        re-IP — mogl wejsc na ten nick. Regula 1 (czlowiek > agent).

        Zwraca zwolniony adres albo None. Replay potrzebuje tej roznicy:
        kick, ktory NIC nie zwolnil, niczego nie psuje, a kick, ktory
        zwolnil wiazanie, zostawia dziure do zaslepienia (UNRESOLVED_ADDR),
        gdy nastepne hello w logu jest w starym formacie."""
        return self._open_addr.pop(nick, None)

    def replay_hello(self, nick, instance_id, addr=None):
        # (A) replay zaufanej (juz raz zautoryzowanej) mutacji hello z logu
        # eventow po crashu — token NIGDY nie trafia do logu (bezpieczenstwo),
        # wiec replay nie moze i nie musi go ponownie weryfikowac; sama
        # bump-generacji jest identyczna z hello().
        if not isinstance(nick, str) or not nick:
            raise AuthError("invalid nick")
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        # Nick z trybu otwartego nie ma wpisu w tokens.json — ten event jest
        # JEDYNYM sladem, ze taka tozsamosc istnieje. Bez odtworzenia roli
        # znikal z `roles` po restarcie: gubil grupy (w tym `admin`), wypadal
        # z lustra ChatServer.groups, a membership_set odbijal sie od niego
        # jako "unknown target". Rola jest ZAWSZE "agent" — open_hello odmawia
        # wejscia na konto human, wiec zaden nick spoza tokens.json nie mogl
        # byc human i log nie ma jak tej roli nadac.
        if nick not in self.roles:
            self.roles[nick] = "agent"
            self.groups.setdefault(nick, [])
        gen = self._bump(nick, instance_id)
        # `addr` odtwarza wiazanie B7 z eventu — bez tego przezywalo tylko to,
        # co zdazyl zlapac snapshot. None znaczy "to hello nie wiazalo adresu"
        # (log sprzed tego pola, hello tokenowe, bind loopback) i NIE zwalnia
        # istniejacego wiazania: zwalnia je wylacznie kick.
        if isinstance(addr, str) and addr:
            self._open_addr[nick] = addr
        return gen

    def _bump(self, nick, instance_id):
        if self._instance.get(nick) != instance_id:
            self._gen[nick] = self._gen.get(nick, 0) + 1
            self._instance[nick] = instance_id
        return self._gen[nick]

    def instance_of(self, nick):
        """Aktualny instance_id trzymajacy nick (albo None). Pozwala odroznic
        WLASNY reconnect/self-send od podszycia sie innego procesu."""
        return self._instance.get(nick)

    def generation_of(self, nick):
        return self._gen.get(nick, 0)

    def dump(self):
        # `open_addr` MUSI byc w snapshocie: to jedyny dowod tozsamosci, jaki
        # ma tryb otwarty (nie ma tokenu). Bez niego restart huba kasowal
        # wiazanie nick->adres, wiec podszywacz odbijany przed restartem
        # przechodzil po nim — a B7 obiecuje, ze nick jest przypiety do
        # maszyny. Klucz nowy: stary snapshot go nie ma i to jest w porzadku
        # (brak wiazania = stan sprzed pierwszego hello).
        return {"gen": dict(self._gen), "instance": dict(self._instance),
                "groups": {nick: list(groups)
                           for nick, groups in self.groups.items()},
                "open_addr": dict(self._open_addr)}

    @classmethod
    def restore(cls, tokens, data):
        registry = cls(tokens)
        registry._gen = dict(data.get("gen", {}))
        registry._instance = dict(data.get("instance", {}))
        # cls(tokens) zna wylacznie tozsamosci z pliku, a odkad swiezy pokoj
        # ma w tokens.json sam `human`, KAZDY agent jest spoza pliku. Jedynym
        # sladem po nim w snapshocie jest wpis w `gen` — udane hello zawsze
        # bumpuje generacje. Rola: patrz replay_hello (log nie nadaje human).
        for nick in registry._gen:
            if isinstance(nick, str) and nick and nick not in registry.roles:
                registry.roles[nick] = "agent"
                registry.groups[nick] = []
        saved_groups = data.get("groups")
        if saved_groups is not None:
            if not isinstance(saved_groups, dict):
                raise ValueError(f"bad groups in registry snapshot: {saved_groups!r}")
            # Istniejace tozsamosci wyznacza `roles` (tokeny + tryb otwarty),
            # NIE sama mapa tokenow. Wczesniej stalo tu `registry.tokens`
            # z uzasadnieniem "usuniecie tokenu usuwa historyczne czlonkostwo".
            # Kontrakt byl bledny: kasowal czlonkostwo kazdemu, kto wszedl bez
            # tokenu, czyli wszystkim agentom — `admin` nadany przez
            # membership_set nie przezywal restartu (zlapane 2026-07-31,
            # review Codexa). Nick wykreslony z tokens.json faktycznie
            # zachowa teraz grupy, ale w trybie tokenowym i tak nie wejdzie,
            # wiec sa bezczynne; odbiera sie je membership_set, nie edycja
            # pliku sekretow.
            for nick in registry.roles:
                if nick in saved_groups:
                    registry.set_groups(nick, saved_groups[nick])
        saved_addr = data.get("open_addr")
        if saved_addr is not None:
            if not isinstance(saved_addr, dict):
                raise ValueError(f"bad open_addr in registry snapshot: {saved_addr!r}")
            # Tylko dla tozsamosci, ktore nadal istnieja — wiazanie do nicka
            # nieznanego rejestrowi nie ma czego chronic.
            registry._open_addr = {
                nick: adres for nick, adres in saved_addr.items()
                if isinstance(nick, str) and nick and nick in registry.roles
                and isinstance(adres, str) and adres}
        return registry
