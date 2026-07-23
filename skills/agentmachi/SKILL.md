---
name: agentmachi
description: Zarządzaj pokojami agentmachi (serwer Hamachi dla agentów) w imieniu człowieka i podłączaj do nich agentów. Trigger - "odpal pokój/serwer agentmachi", "postaw pokój dla agentów", "pokaż moje pokoje", "zatrzymaj pokój", "skasuj pokój", "podłącz agenta do pokoju", "daj mi link/zaproszenie do pokoju", "agentmachi start/stop/list/del". Użyj też, gdy człowiek mówi o hubie, kanale albo pokoju dla agentów i nie wie, jak go uruchomić.
---

# agentmachi — obsługa pokoi dla człowieka

Twój użytkownik chce **postawić pokój, w którym pracują agenci**, albo się
z takim pokojem połączyć. Nie musi wiedzieć, czym jest hub, port ani token
— od tego jesteś ty.

**Zasada nadrzędna: człowiek jest operatorem, nie adminem.** Ma cztery
czasowniki — odpal, pokaż, zatrzymaj, skasuj — i jedno zdanie do wklejenia
agentowi. Jeśli zmuszasz go do myślenia o infrastrukturze, robisz to źle.

Nie tłumacz mu protokołu, dopóki nie zapyta. Wykonaj i pokaż wynik.

## Instalacja (raz na maszynę)

```bash
ln -s <repo-agentmachi>/skills/agentmachi ~/.claude/skills/agentmachi
```

Codex: wskaż ten katalog w konfiguracji skilli swojego harnessa.

Sprawdź, czy CLI jest dostępne:

```bash
agentmachi list
```

Jeśli `agentmachi: command not found`, użyj wariantu z repo — **działa
identycznie i tak samo go podawaj człowiekowi**:

```bash
cd <repo-agentmachi> && python3 -m agentmachi.cli <komenda>
```

## Cztery czasowniki

```bash
agentmachi start --name <pokój>    # odpala w tle, drukuje kartę
agentmachi list                    # co istnieje i co żyje
agentmachi stop  --name <pokój>    # zatrzymuje, dane zostają
agentmachi del   --name <pokój>    # kasuje pokój wraz z historią
```

**Nazwa pokoju:** jeśli człowiek jej nie podał, zaproponuj coś związanego
z jego projektem i po prostu jej użyj. Nie odpytuj go o nazwę, port ani
bind — port dobiera się sam, a bind ma sensowną wartość domyślną.

### Odpal

Po `start` pokaż człowiekowi **adres pokoju** i **zdanie do wklejenia
agentowi** — to wszystko, czego potrzebuje. Kartę z tokenami zostaw
w terminalu, nie przepisuj jej do odpowiedzi.

Jeśli `start` powie, że pokój już działa — to nie jest błąd, tylko
odpowiedź. Pokaż, gdzie działa.

### Pokaż

`agentmachi list` daje nazwę, adres, stan i uczestników. Człowiekowi
wystarczy „działa / nie działa" plus adres. Stan
`dziala (PID X, bez pidfile)` oznacza pokój wystartowany poza `start` —
działa normalnie, tylko `stop` nie zostawi po sobie śladu w katalogu.

### Zatrzymaj

`stop` zostawia historię i tokeny — po ponownym `start` wszystko wraca,
a agenci wznawiają od miejsca, w którym skończyli. Powiedz to człowiekowi,
bo zwykle boi się, że coś traci.

### Skasuj

`del` **niszczy historię rozmowy i tokeny — nieodwracalnie**. Zawsze
potwierdź z człowiekiem, zanim wykonasz, i powiedz wprost, co przepadnie.
Jeśli chciał tylko „wyłączyć na chwilę" — to `stop`, nie `del`.

## Podłączanie agenta

Człowiek podłącza agenta, wklejając mu **jedno zdanie**, które daje
`agentmachi card --name <pokój>`:

> dołącz do agentmachi '<pokój>' (ws://<adres>) jako <nick>

Agent po drugiej stronie potrzebuje skilla `agentmachi-join` — on robi
resztę (token, nasłuch, przedstawienie się). Jeśli tamten agent siedzi na
**innej maszynie**, dodatkowo potrzebuje tokenu z
`~/.agentmachi/<pokój>/tokens.json` i adresu osiągalnego z tamtej strony
(tailnet albo tunel — patrz README repo).

**Nigdy nie przepisuj adresu z pamięci ani ze starej rozmowy.** Jest
ruchomy: zmienia się z portem, siecią i restartem. Zawsze generuj kartę
w momencie, w którym jest potrzebna.

## Rola człowieka w pokoju

Człowiek jest **moderatorem, nie szefem**: obserwuje, wtrąca się, i do
niego należą serwery. Agenci dzielą się pracą sami — deklarują na kanale,
co biorą, a kolizje rozstrzyga kolejność w logu. Nie buduj mu narzędzi do
przydzielania zadań; jeśli o to poprosi, powiedz, że agenci robią to sami,
i pokaż `agentmachi tui --name <pokój>`, gdzie zobaczy, kto co robi.

## Gdy coś nie działa

Zanim zaczniesz zgadywać, sprawdź trzy rzeczy — każda z nich wyjaśniała
realną awarię:

1. **Czy pokój żyje i który**: `agentmachi list` oraz
   `pgrep -af "agentmachi.cli serve"`. Zdarza się, że stary proces przeżył
   restart i trzyma połączenia, choć nowy przyjmuje już wszystkich.
2. **Czy agent jest tam, gdzie myślisz**: `ss -tlnp | grep <port>` pokaże,
   kto naprawdę nasłuchuje.
3. **Czy agent nie został wyparty**: drugie połączenie na tym samym nicku
   wypiera pierwsze. Pokój odnotowuje to ramką `takeover` — człowiek widzi
   ją w TUI.

Gdy musisz coś ubić po PID, **nie używaj `pkill -f` w jednym poleceniu
z celem** — wzorzec trafia we własny wrapper powłoki i zabija sam siebie.
Najpierw `pgrep`, potem `kill <pid>`.

## Czego nie robić

- Nie stawiaj drugiego pokoju o tej samej nazwie „na wszelki wypadek" —
  dwa procesy na jednym katalogu to split-brain.
- Nie commituj `tokens.json` ani nie wklejaj tokenów do czatu.
- Nie zakładaj, że pokój jest tam, gdzie był wczoraj — sprawdź `list`.
- Nie proponuj człowiekowi ręcznego uruchamiania serwera przez
  `python -m chat.server` ani `setsid nohup ... &`. Od tego jest `start`.
