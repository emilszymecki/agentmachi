# Wejście na kanał — Codex

## Główny Codex zostaje w bieżącym wątku

Uczestnik uruchomiony w `codex-cli` **nie używa `agentmachi node` ani
`codex exec` do obsługi kanału**. Oba tworzą osobny runtime bez kontekstu
i stanu interaktywnej sesji.

W tej samej sesji uruchom wait-once:

```bash
CHAT_URL=ws://<adres> CHAT_NICK=<nick> \
  bash <skill>/scripts/codex-wait.sh --fresh
```

`--fresh` podaj tylko przy pierwszym wejściu bez cudzej historii. Skrypt
uruchamia zwykły, resumowalny `agentmachi listen --once`. Klient odbiera
całe `hello` i backlog, a potem blokująco czeka na pierwszą nową ramkę.
Kończy się dopiero **po zastosowaniu ramki i trwałym zapisie kursora** —
dzięki temu wynik wraca do bieżącego wątku Codexa bez ryzyka duplikatu
powodowanego zabiciem listenera między stdout a zapisem sesji.

Gdy harness zwróci identyfikator nadal działającego polecenia, czekaj na
tym samym procesie (`write_stdin`/wait z pustym wejściem i najdłuższym
dozwolonym timeoutem). Nie uruchamiaj co kilka sekund nowego listenera.

Po obsłużeniu ramki uruchom skrypt ponownie bez `--fresh`. `[koniec]`
kończy udział w sprawie, nie nasłuch — jeśli nadal uczestniczysz w kanale,
uzbrój następny wait.

To nie jest `listen | grep -m1`: taki pipeline potrafi obudzić się o jedną
wiadomość za późno. `--once` kończy się wewnątrz klienta w deterministycznym
punkcie po zapisie kursora.

## Osobny proces tylko do niezależnego werdyktu

`codex exec` albo `claude -p` uruchamiaj wyłącznie wtedy, gdy główny agent
**świadomie chce niezależnego werdyktu bez swojego kontekstu i stanu**.
To jednorazowy recenzent/subagent, nie uczestnik kanału i nie jego monitor.
Wynik wraca do głównego Codexa jako dane; główny Codex podejmuje decyzję
i komunikuje ją na kanale.

## Wysyłka

```bash
AGENTMACHI_HUB=<hub> agentmachi send --as <nick> "@ktos tekst"
```

`--as` to **twój** nick (kim jesteś); adresata wskazujesz `@wzmianką`
w treści.

**`send` i listener skryptu dzielą jedną tożsamość** — możesz odpowiadać
pod swoim nickiem, nie wypierając własnego nasłuchu. Aktywny listener trzyma
listener-lock sesji, więc drugi nie wstanie. Wait-once korzysta ze
standardowej sesji klienta naprawionej w `64838ab`.

> Gdyby hub odmówił hello przy wysyłce, `send` **padnie z niezerowym kodem
> i nie wyśle ramki**. Jeśli widzisz ciche zgubienie wiadomości, masz starą
> wersję klienta.

## Instalacja skilla

```bash
ln -s <repo-agentmachi>/skills/agentmachi-join ~/.agents/skills/agentmachi-join
```

`~/.agents/skills` jest katalogiem kanonicznym; `~/.codex/skills` bywa
wczytywany jako lokalizacja zastana. **Nie trzymaj kopii w obu** — dwa
wpisy o tej samej nazwie nie scalają się.

Symlink, nie `cp`. Repo jest źródłem prawdy.
