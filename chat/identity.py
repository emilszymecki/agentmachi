"""Tozsamosc logiczna: nick + instance_id -> generation. Token per agent."""

import hmac


class AuthError(Exception):
    pass


class Registry:
    def __init__(self, tokens):
        for nick, token in tokens.items():
            if not isinstance(nick, str) or not nick:
                raise ValueError(f"bad nick in tokens map: {nick!r}")
            if not isinstance(token, str) or not token:
                raise ValueError(f"bad token for nick {nick!r}: {token!r}")
        self.tokens = dict(tokens)    # nick -> token (kopia — odporne na mutacje wywolujacego)
        self._gen = {}                # nick -> int
        self._instance = {}           # nick -> aktualny instance_id

    def hello(self, nick, instance_id, token):
        if nick not in self.tokens:
            raise AuthError(f"bad token for {nick}")
        expected = self.tokens[nick]
        if not isinstance(token, str) or not token:
            raise AuthError(f"bad token for {nick}")
        if not hmac.compare_digest(expected, token):
            raise AuthError(f"bad token for {nick}")
        if not isinstance(instance_id, str) or not instance_id:
            raise AuthError(f"bad instance_id for {nick}")
        if self._instance.get(nick) != instance_id:
            self._gen[nick] = self._gen.get(nick, 0) + 1
            self._instance[nick] = instance_id
        return self._gen[nick]

    def generation_of(self, nick):
        return self._gen.get(nick, 0)

    def is_current(self, nick, generation):
        return self._gen.get(nick) == generation

    def dump(self):
        return {"gen": dict(self._gen), "instance": dict(self._instance)}

    @classmethod
    def restore(cls, tokens, data):
        registry = cls(tokens)
        registry._gen = dict(data.get("gen", {}))
        registry._instance = dict(data.get("instance", {}))
        return registry
