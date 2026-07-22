# Plan B2: agentmachi jako samodzielne narzędzie

Data: 2026-07-23. Autor: beta (solo, po zamknięciu B1).
Zasada nadrzędna: **LESS IS MORE** — każdy punkt zakresu musi być śladem
konkretnego bólu z dogfoodu, nie przewidywaniem. Punkt bez bólu = out.

## Cel (wizja Emila, dosłownie)

1. Prosta komenda odpala serwer.
2. Dostajesz adres + listę działających agentów.
3. Skill dla Claude Code i Codexa: jak się połączyć.
4. Łączą się i współpracują — jak Hamachi i CS.

Ból, który to leczy (dogfood): serwer, tokeny i dane mieszkają dziś
W REPO PROJEKTU — agent musi robić `cd` do środka, tokeny leżą obok
kodu, uruchomienie wymaga znajomości env-varów i aktywnego data_dir
("kompletna dupa" — Emil).

## Zakres: DWA taski

### t3 — pakiet `agentmachi` (CLI serve)

- Pakowanie: `pyproject.toml`, pakiet `agentmachi` (obecny `chat/` +
  `tui.py` + klient), instalacja `uvx agentmachi` / `pip install`.
- `agentmachi serve [--name domyslny] [--port 8766]`:
  - dane huba w `~/.agentmachi/<name>/` (tokens.json 0600, rules.md,
    data/ z event-logiem) — tworzone przy pierwszym starcie z sensownymi
    defaultami (tokeny generowane, rules przykładowe),
  - po starcie drukuje **kartę wejściową**: adres ws://, ścieżka tokenów,
    lista podłączonych agentów ze statusami (participants snapshot),
    gotowe komendy join do wklejenia agentom,
- `agentmachi tui [--name]` — obecne TUI, czyta config z `~/.agentmachi/`,
- `agentmachi send <nick> "tekst"` / `agentmachi listen` /
  `agentmachi heartbeat <task_id>` — obecny send.py jako subkomendy,
- ZERO nowych mechanik serwera. Wyłącznie przepakowanie + ścieżki.
- Sprzątek przy okazji (bez osobnych punktów): dead `is_current` /
  `make_envelope`, unifikacja formatu `activation_id` na `nick:seq`.
- Akceptacja: na CZYSTYM katalogu (poza repo!) `uvx agentmachi serve`
  wstaje, karta wejściowa się drukuje, TUI się łączy, agent dołącza
  komendą z karty. Repo projektu nie dostaje ŻADNEGO nowego pliku.

### t4 — skill `agentmachi:join` (CC + Codex)

- Jeden skill, dwa harnessy (sekcje per harness jak w AGENTS.md):
  - CC: Monitor(command: `agentmachi listen`), wysyłka `agentmachi send`,
  - Codex: PTY listener + /goal (wzorzec codexa z AGENTS.md).
- Wejście w języku naturalnym: "dołącz do agentmachi <adres> jako <nick>"
  → skill: token z karty/env, hello, nasłuch, przedstawienie się,
  deklaracja `status idle`.
- **Auto-heartbeat przy claimie** (część joina, nie feature): claim →
  skill odpala `agentmachi heartbeat <task_id>` w tle, ubija przy done.
  (Ból: lease wygasł mi 3× w trakcie pracy przy ręcznej mechanice.)
- Respektowanie rules z `session_metadata` + kanonu statusów.
- Akceptacja: świeża sesja CC dostaje jedno zdanie i po 2 minutach jest
  na kanale ze statusem idle; bierze task z ofertą bez wygaśnięcia lease.

## Jawnie POZA zakresem (YAGNI — wraca tylko po realnym bólu)

- `task_release` (expiry wystarcza — sprawdzone 3× w praktyce),
- SSH/git-gate/forced-command (to B3: dwie maszyny),
- MCP-klient czatu (odrzucony już w kroku B),
- tryb "matki" w skillu (decyzja Emila: płynne grupy + rules.md),
- multi-hub/multi-pokój, web-front, revocation/role_epoch,
- wszelka konfiguracja ponad `--name`/`--port`.

## Aktualizacja specu (przy t3, jednym commitem)

Spec `statek-matka-krok-b`: adnotacja na górze — koncepcja
dedykowanego orkiestratora ZASTĄPIONA płynnymi grupami + rules.md
(potwierdzone praktyką B1); hierarchia = tekst w rules, nie rola.

## Kolejność

t3 → t4 (skill woła komendy z t3). Po t4: test końcowy = scenariusz
Hamachi: Emil odpala `agentmachi serve` + `agentmachi tui`, daje dwóm
świeżym sesjom po jednym zdaniu, patrzy jak współpracują.

## Stan realizacji (aktualizowany na bieżąco)

- [x] Plan spisany i zaakceptowany kierunkowo przez Emila (2026-07-23)
- [x] Karty t3 i t4 wystawione na hubie (obie `open v1`, HEAD 489bd2a)
- [x] t3 — pakiet agentmachi: ZAIMPLEMENTOWANY (pyproject + agentmachi/cli.py:
      serve/card/tui/send/listen/heartbeat, dane w ~/.agentmachi/<name>/,
      karta wejściowa, tui.py na env; smoke na czystym katalogu ZIELONY:
      serve+card+send+listen z wygenerowanym tokenem; sprzątek done:
      make_envelope/is_current usunięte, format activation_id ujednolicony
      przez eliminację drugiego; 260 testów). CZEKA: review + approve.
- [ ] t4 — skill join: NIEZACZĘTY (czeka na t3)
- [x] adnotacja w specu statek-matka (w commicie t3)

### Jak wrócić (checklist na start sesji)

1. Sekwencja z CLAUDE.md: sprawdź hub (`pgrep -af chat.server`; jeśli
   padł: `CHAT_TOKENS=hub.tokens.json CHAT_PORT=8766
   CHAT_DATA=chat-data/dogfood-842b71a python3 -m chat.server`,
   setsid+nohup+disown), Monitor(command: send.py --listen), status idle.
2. Przeczytaj ledger `.superpowers/sdd/progress.md` (sekcja B1 ZAMKNIĘTE
   + ta sekcja) — NIE re-dispatchuj niczego z B1.
3. Claim t3 (`expected_task_version` = aktualna z oferty) + OD RAZU
   heartbeat w tle (`send.py --heartbeat t3`).
4. Implementuj wg karty t3 wyżej; commit na branchu `b1-serwer` (albo
   nowym `b2-narzedzie` od main — main == B1).
5. Tryb: solo (beta = head+worker); review t3 zrobi Emil/przyszły
   reviewer; self-approve tylko za jawną zgodą Emila.
