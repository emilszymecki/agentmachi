# Sesja odejmowania — raport

**Data:** 2026-09-01. **Zakres:** gorąca ścieżka agentmachi.
**Baza porównania:** `2042da5` (commit przed pierwszym cięciem).
**Suita:** 710 passed po każdym z 14 commitów.

Brzytwa: do każdej linii jedno pytanie — czy jej przeczytanie zmienia
decyzję agenta w tej sesji. Nie → wycięte. Tak → zostaje w formie
„co i kiedy". Niczego nie dopisano.

---

## Liczby per plik

| plik | linie | bajty | |
|---|---|---|---|
| `agentmachi/howto_default.md` | 105 → 99 | 5089 → 4763 | −6% |
| `skills/claude/agentmachi-join/SKILL.md` | 89 → 84 | 4049 → 3689 | −8% |
| `skills/codex/agentmachi-join/SKILL.md` | 88 → 88 | 4066 → 4032 | −0% |
| `claude/…/references/claude-code.md` | 439 → 372 | 22854 → 17701 | **−22%** |
| `claude/…/references/troubleshooting.md` | 357 → 327 | 17318 → 15116 | −12% |
| `claude/…/references/collaboration.md` | 125 → 104 | 5918 → 4528 | **−23%** |
| `claude/…/references/codex.md` | 142 → 137 | 6807 → 6405 | −5% |
| `codex/…/references/codex-runtime.md` | 219 → 204 | 11589 → 10332 | −10% |
| `codex/…/references/troubleshooting.md` | 112 → 109 | 4585 → 4381 | −4% |
| `codex/…/references/collaboration.md` | 83 → 82 | 3306 → 3222 | −2% |
| `skills/claude/agentmachi/SKILL.md` | 230 → 213 | 10123 → 9114 | −9% |
| `skills/codex/agentmachi/SKILL.md` | 168 → 167 | 5789 → 5709 | −1% |
| `CLAUDE.md` | 286 → 212 | 16222 → 11705 | **−27%** |
| `AGENTS.md` | 280 → 262 | 17403 → 15890 | −8% |
| **razem** | **2723 → 2460** | **135118 → 116587** | **−13%** |

Szablon `KONTRAKT` (obie kopie `integrate_project.py`): 26 → 25 linii,
1602 → 1544 B przy limicie 2048.

## Sufity po cięciu

| plik | rozmiar / sufit | luz | zmiana sufitu |
|---|---|---|---|
| `CLAUDE.md` | 11705 / **12288** | 583 | 16384 → 12288 |
| `AGENTS.md` | 15890 / **16384** | 494 | 17408 → 16384 |
| `howto_default.md` | 4763 / 5120 | 357 | bez zmian |
| `claude/…/SKILL.md` | 3689 / 4096 | 407 | bez zmian |
| `codex/…/SKILL.md` | 4032 / 4096 | 64 | bez zmian |

Trzech progów nie ruszono świadomie: te pliki są już na „nowy rozmiar
plus mały luz", a dobicie progu do krawędzi to tryb awarii opisany
w `tests/test_skills.py` przy wpisach z 2026-08-01 i 2026-08-06 — sufit
przy krawędzi przestaje wymuszać zwięzłość i zaczyna blokować
prostowanie nieprawdy.

Zamek sfalsyfikowany: dopisanie 1 KB do `CLAUDE.md` czerwieni
`test_budzety_kontekstu_agenta`.

---

## Co przeniesiono (nie usunięto — było już w celu linku)

| co | skąd | dokąd |
|---|---|---|
| lista fizyki huba + historia rate-limitu | `CLAUDE.md`, `AGENTS.md`, `skills/*/agentmachi/SKILL.md` | [`docs/philosophy.md`](philosophy.md), [`docs/pl/konstytucja.md`](konstytucja.md), `README.md`, `CONTRIBUTING.md` |
| pełne historie z pomiarami przy regułach współpracy | `claude/…/collaboration.md` (`*Cost of not doing it:*`) | [`docs/pl/zasady-agentyczne.md`](zasady-agentyczne.md) — link stoi w stopce tego pliku od początku |
| powód zakazu `grep -m1` (SIGPIPE) | `CLAUDE.md` | `howto_default.md` — wersja kanoniczna, 3 linie |
| historia „ten plik kłamał o wejściu bez nicka" | `CLAUDE.md` | [`docs/pl/zasady-agentyczne.md`](zasady-agentyczne.md) (sprawdzaj całą drogę, nie ostatni artefakt) |
| mechanizm `howto` z drzewa roboczego | `CLAUDE.md` (incydent) | [`docs/pl/runbook-migracja-kanalu.md`](runbook-migracja-kanalu.md) — link już był |

## Czego świadomie nie tknięto

**`agentmachi/skills/README.md`** (77 linii) — poza wskazanym zakresem:
to nie `SKILL.md` ani plik z `references/`, nie ładuje się do kontekstu
żadnego agenta automatycznie.

**Wszystkie przepisy diagnostyczne.** Grep przed/po na każdym ciętym
pliku: `grep -m1`, `ss -tlnp`/`-tnp`, `pgrep`/`ps -o comm=`, kursor
(glob vs `sha256(hub+nick)`), reconnect/resync, ghost-check, wybór
interpretera (`-P`, `command -v`, Python zamiast bash/zsh/dash),
`LISTENER ENDED`, kod 4003, `wake_filter`, `--fresh`, `--json`,
`instance_id`, `suggested_nick`, `CHAT_NICK`, `codex-wait.sh`,
`listen --once`, `Monitor`. Żaden licznik nie spadł do zera.

**Tabela granic z probe'ami w `AGENTS.md`** — trzy wiersze, kolumna Typ
i wszystkie cztery komendy probe bez zmian.

**Pięć punktów kontraktu + akapit o innych agentach** — punkty co do
jednego, razem z „working alone is the normal case and needs no
justification". Wypadło jedno zdanie powtarzające punkt 1.

**Flagi niezmierzonego przy Codeksie** — `codex-runtime.md` i `codex.md`
cięte wyłącznie w formie, nigdy w twierdzeniu. Zostały wszystkie trzy:
parser `/goal` nieudokumentowany, „whether a given harness renders a copy
control is **not measured** here" z otwartym pomiarem dla kogoś, kto ma
UI przed sobą, oraz „the bare-block variant has not been measured
separately". Powód w [`docs/pl/zasady-agentyczne.md`](zasady-agentyczne.md):
cudzy runtime to hipoteza, nie obserwacja.

**`howto_default.md` przy `grep -m1`** — trzy linie o SIGPIPE zostają
w całości, bo `CLAUDE.md` odsyła teraz właśnie tutaj.

## Parytet wariantów po cięciu

Sprawdzony gerpem po tematach, nie po tekście:

- `agentmachi` (operator): **19/19** zgodnych
- `collaboration.md`: **14/14**
- `troubleshooting.md`: 14/15
- `agentmachi-join/SKILL.md`: 12/14

Oba rozjazdy są **sprzed tej sesji**, potwierdzone przez `git stash`
na stanie bazowym, i nic do nich nie dopisano, bo to sesja odejmowania:

1. Elementarza „wzmianka budzi, chat bez wzmianki idzie do ludzi" nie ma
   **nigdzie po stronie Codeksa** — ani w `SKILL.md`, ani w żadnym
   `references/`. Jedynym źródłem jest `howto` przy hello.
2. `troubleshooting.md` Codeksa ma „notification is a pointer, not the
   message"; po stronie Claude'a ta reguła mieszka w `collaboration.md`
   i `claude-code.md`, których Codex u siebie nie ma.

Jeśli któryś ma zostać wyrównany, to jest osobna decyzja i osobny commit
— dopisanie, nie odjęcie.

## Ślad w gicie

14 commitów, jeden na plik, każdy z `docs(hot):` i licznikiem linii
w tytule; cofnięcie dowolnego pojedynczego pliku to jeden `git revert`.

```
29c80f0 test(hot): sufity BUDZETY schodzą za cięciem
e4792b6 docs(hot): AGENTS.md — 280 → 262 linii
6da9a70 docs(hot): CLAUDE.md — 286 → 212 linii
34ea729 docs(hot): szablon KONTRAKT — 26 → 25 linii (obie kopie)
5284d68 docs(hot): codex/references/troubleshooting.md — 112 → 109
e8f97c4 docs(hot): claude/references/codex.md — 142 → 137
0d449a9 docs(hot): codex/agentmachi/SKILL.md — 168 → 167
eb7ff0c docs(hot): claude/agentmachi/SKILL.md — 230 → 213
34a5341 docs(hot): codex/references/collaboration.md — 83 → 82
457ffdd docs(hot): claude/references/collaboration.md — 125 → 104
82a008a docs(hot): references/codex-runtime.md — 219 → 204
a0c7730 docs(hot): references/troubleshooting.md — 357 → 327
e7640df docs(hot): references/claude-code.md — 439 → 372
20181f1 docs(hot): codex/agentmachi-join/SKILL.md — 88 → 88
3e5cbf1 docs(hot): howto_default.md — 105 → 99
```

Efektu nie mierzono — ocenia go operator w pracy.
