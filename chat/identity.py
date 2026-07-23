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

_VALID_ROLES = ("agent", "human")


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

    def role_of(self, nick):
        return self.roles.get(nick, "agent")

    def groups_of(self, nick):
        return self.groups.get(nick, [])

    def set_groups(self, nick, groups):
        """Ustaw plynna funkcje operacyjna; role agent/human pozostaje stala."""
        if not isinstance(nick, str) or not nick or nick not in self.tokens:
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

    def open_hello(self, nick, instance_id):
        """B6: wejscie BEZ tokenu (tryb otwarty — patrz ChatServer.open_mode).

        Tozsamosc opiera sie na sieci i moderacji czlowieka, nie na sekrecie:
        do huba dosiegnie tylko maszyna z tailnetu, a moderator widzi kazde
        wejscie i moze je odwolac (`kick`). Token zostaje wylacznie dla roli
        human — bez tego dowolny uczestnik tailnetu wszedlby jako moderator
        i wyrzucal pozostalych.

        Nick nieznany dostaje role agenta i grupe `workers`: bez grupy bylby
        technicznie na kanale i praktycznie gluchy, bo wzmianki `$workers`
        chodza po grupach. Nick znany z tokens.json zachowuje swoja
        konfiguracje (grupy z pliku), tylko nie musi dowodzic tokenem.
        """
        if not isinstance(nick, str) or not nick:
            raise AuthError("invalid nick")
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        if self.roles.get(nick) == "human":
            raise AuthError(
                f"{nick} to konto moderatora — wejscie wymaga tokenu")
        if nick not in self.roles:
            self.roles[nick] = "agent"
            self.groups[nick] = ["workers"]
        return self._bump(nick, instance_id)

    def replay_hello(self, nick, instance_id):
        # (A) replay zaufanej (juz raz zautoryzowanej) mutacji hello z logu
        # eventow po crashu — token NIGDY nie trafia do logu (bezpieczenstwo),
        # wiec replay nie moze i nie musi go ponownie weryfikowac; sama
        # bump-generacji jest identyczna z hello().
        if not isinstance(nick, str) or not nick:
            raise AuthError("invalid nick")
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        return self._bump(nick, instance_id)

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
        return {"gen": dict(self._gen), "instance": dict(self._instance),
                "groups": {nick: list(groups)
                           for nick, groups in self.groups.items()}}

    @classmethod
    def restore(cls, tokens, data):
        registry = cls(tokens)
        registry._gen = dict(data.get("gen", {}))
        registry._instance = dict(data.get("instance", {}))
        saved_groups = data.get("groups")
        if saved_groups is not None:
            if not isinstance(saved_groups, dict):
                raise ValueError(f"bad groups in registry snapshot: {saved_groups!r}")
            # Biezaca mapa tokenow wyznacza istniejace tozsamosci. Usuniecie
            # tokenu usuwa tez historyczne czlonkostwo; nowy nick bierze grupy
            # z aktualnej konfiguracji.
            for nick in registry.tokens:
                if nick in saved_groups:
                    registry.set_groups(nick, saved_groups[nick])
        return registry
