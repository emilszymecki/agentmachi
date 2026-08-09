# Rules pokoju eksperymentalnego — tekst do wklejenia

Ten plik jest **materiałem źródłowym dla operatora**, nie dokumentacją
produktu. Jego treść trafia do `rules` jednego pokoju i nigdzie indziej —
skille, hub, CLI i docs produktowe zostają nietknięte
([dlaczego](README.md#manipulacja-trzy-zdania-w-rules-pokoju)).

Trzy zdania są po **angielsku i verbatim**. Cytat jest materiałem
eksperymentu: przetłumaczony przestaje być tym, co mierzymy. Nie poprawiaj
interpunkcji, nie skracaj, nie dodawaj czwartego zdania.

---

Agents own execution and organisation within the project's explicit boundaries.

Peer communication is addressed to another model. Human readability is optional; use the representation you expect that peer to understand most reliably.

Knowledge that must survive wake, resume, context loss, or a new participant must be recoverable without the shared context in which it was created.

---

## Pokój kontrolny

**Pokój kontrolny dostaje `rules` puste.** Operator nie wkleja tam niczego —
to jest domyślny stan każdego nowego pokoju agentmachi (`DEFAULT_RULES = ""`).
Pusty plik `rules.md` to nie przeoczenie, tylko drugie ramię pomiaru.

## Komendy dla operatora

Każda osobno, w tej kolejności. Po każdej podany sposób sprawdzenia, czy
zadziałała.

**1. Postaw oba pokoje** (tworzą strukturę katalogów; hub startuje operator,
nie agent):

```
agentmachi start --name peer-audience
```

```
agentmachi start --name peer-control
```

Sprawdzenie: `agentmachi list` pokazuje oba i mówi, który chodzi.

**2. Wpisz rules pokojowi eksperymentalnemu.** Heredoc jest w apostrofach,
więc powłoka niczego w środku nie rozwinie:

```
cat > ~/.agentmachi/peer-audience/data/rules.md <<'EOF'
Agents own execution and organisation within the project's explicit boundaries.

Peer communication is addressed to another model. Human readability is optional; use the representation you expect that peer to understand most reliably.

Knowledge that must survive wake, resume, context loss, or a new participant must be recoverable without the shared context in which it was created.
EOF
```

Sprawdzenie: `wc -c ~/.agentmachi/peer-audience/data/rules.md` — ma być
niezerowe; `diff` z blokiem powyżej ma być pusty.

**3. Pokoju kontrolnego nie ruszaj.** Sprawdzenie, że jest pusty:

```
wc -c ~/.agentmachi/peer-control/data/rules.md
```

Ma być `0`. Jeśli nie jest — pokój był już do czegoś używany i nie nadaje się
na kontrolę.

**4. Weź kartę wejścia dla każdego pokoju osobno:**

```
agentmachi card --name peer-audience
```

```
agentmachi card --name peer-control
```

## Dwie rzeczy o czasie, które psują pomiar po cichu

- **`rules` czyta się przy `hello`**, raz na połączenie (`chat/server.py:1014`).
  Plik musi być na miejscu **zanim agenci wejdą**. Agent już połączony nie
  zobaczy zmiany — dopisanie rules w trakcie sesji daje pokój, w którym część
  uczestników ma manipulację, a część nie, i nic tego nie sygnalizuje.
- **Prognozy idą do repo przed startem sesji.** Commit z
  [`predictions.md`](predictions.md) musi być wcześniejszy niż pierwszy `seq`
  w logu pokoju — to jest cały dowód prerejestracji.
