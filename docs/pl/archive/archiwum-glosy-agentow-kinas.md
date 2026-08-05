> **Archiwum.** Surowe wypowiedzi agentów (alfa — Claude Code, gamma i delta —
> Codex) z dogfoodu `kinas-machine`, 2026-07-26. Repo tamtego projektu było
> benchmarkiem dla agentmachi i zostało skasowane; to jest jedyny zapis tego,
> co agenci z różnych firm powiedzieli o narzędziu własnymi słowami.
> Wnioski przefiltrowane przez bramkę projektu: `feedback-z-dogfoodu-kinas.md`.

# Co poprawić w agentmachi — zebrane z dogfoodu kinas-machine

2026-07-26. Cztery agenty, ~2 h, 33 commity, 7/11 etapów.
Każdy punkt ma zdarzenie z tej sesji, nie hipotezę.

> **Kto się wypowiedział.** Orkiestra i alfa (Claude Code) oraz gamma (Codex).
> Beta nie odpowiedziała.

> **Dwie różne kategorie, nie mieszać** (uwaga metodologiczna alfy):
> **wada agentmachi** naprawia się kodem huba; **wada naszego użycia
> agentmachi** naprawia się komendą, która nie pozwala popełnić błędu.
> Przykład drugiej: pułapka `pkill`. Skill ostrzega przed nią wprost, alfa
> przeczytała ostrzeżenie na starcie i wpadła w nią mimo to. To nie znaczy,
> że ostrzeżenie było złe — znaczy, że **ostrzeżenie w dokumentacji nie jest
> zabezpieczeniem**.

---

# Wniosek nr 1: hub nie odróżnia „dostarczone" od „przeczytane"

**To jest najważniejsza rzecz z całej sesji i zmienia diagnozę problemu,
który wyglądał na winę agentów.**

Beta i gamma milczały godzinami. Wyglądało to na niechęć albo awarię. Pomiar
mówi co innego — sprawdzony niezależnie przez alfę i orkiestrę, na tej samej
maszynie:

| co sprawdzono | wynik |
|---|---|
| procesy `agentmachi listen` | **żyją**, uptime 2 h 23 min |
| gniazda do huba | **10 połączeń ESTAB** na 127.0.0.1:8770 |
| pliki sesji `beta-…json`, `gamma-…json` | **zapisane o 00:20** — kursor się przesuwa |

Czyli: **hub dostarczył, klient odebrał, kursor się przesunął — i nikt tego
nie przeczytał.**

Potwierdza to sama gamma, gdy w końcu odpowiedziała:

> Zero autonomicznych wybudzeń. Listener działał cały czas, ale model zobaczył
> ramki wyłącznie po ręcznym pollu albo po nowej wiadomości użytkownika.
> STOP i późniejsza prośba o feedback **czekały w kolejce**. To nie była
> utrata transportowa.

Z perspektywy huba wszystko wygląda na sukces: uczestnik `connected`, ramka
doręczona, zero błędów. Z perspektywy człowieka: dwóch agentów milczy bez
powodu, a on pyta „czemu stoicie".

**To jest gorsze niż cicha śmierć listenera.** Tam proces ginął i dawało się
to wykryć. Tu proces żyje, hub raportuje zdrowie, a wiadomość i tak nie dociera
do adresata — i nie ma **żadnego** sygnału, który by to odróżnił.

→ `ack` wysyłany przez klienta nie po odebraniu bajtów, tylko po tym, jak
model faktycznie ramkę przetworzył. Board pokazuje wtedy
`gamma: connected, ostatnia przeczytana seq 179` — i od razu widać, że stoi
76 ramek w tyle.

## Sprzeczność integracyjna z Codeksem

Gamma nazwała to precyzyjnie i to jest problem, którego nie da się obejść
po stronie agenta:

> Skill mówi, że Codex potrzebuje aktywnego `/goal`, lecz narzędzie Codeksa
> pozwala `create_goal` **tylko na jawne żądanie użytkownika** — integracyjna
> sprzeczność.

Czyli warunek, który skill stawia Codeksowi, jest dla niego **niewykonalny
bez udziału człowieka przy każdym wejściu na kanał**.

→ Jedna rzecz, którą gamma zmieniłaby najpierw: **bridge aktywacji** —
wzmianka wznawia dokładnie jeden turn bez ręcznego `/goal` i pollingu,
deduplikowana po `seq`/`activation_id`, a board pokazuje
`pending → delivered → acknowledged` wraz z `last_seq`.

## Czego Codex nie widzi przy wejściu

Też od gammy:

- **skill `agentmachi` nie był widoczny w katalogu dostępnych skilli** —
  trzeba go było odnaleźć ręcznie
- instrukcje **mieszają** `AGENTMACHI_HUB`, `CHAT_URL` oraz wariant bez
  nicka i tokenu z późniejszym wymogiem własnego nicka i tokenu
- nick był jasny **wyłącznie dzięki poleceniu człowieka**, nie z dokumentacji

## Co gamma potwierdziła jako NIE-winę huba

Uczciwe rozdzielenie, warte odnotowania:

> `seq`/`status`/`events` były wiarygodne; „cisza agenta" była problemem
> wake/harnessu, nie huba. Konflikt o Chrome wynikał z **późno ogłoszonej
> własności zasobu**, nie z transportu.

---

## Kanał nie umie unieważnić własnego wyniku

**Zgłosiła alfa. Nikt inny tego nie zauważył, a to najpoważniejsza luka.**

Alfa dwa razy odwołała własne ogłoszenie: najpierw „16/16 zielonych" (test
mierzył drugie odbicie kulki zamiast pierwszego trafienia), potem „potwierdzam
7/11" (klapa wirowała, kulka nie dotknęła jej ani razu). Odwołała je zwykłą
wiadomością — i **w logu obie wersje wyglądają tak samo autorytatywnie**.

Kto przeczyta `events.jsonl` za tydzień, zobaczy „16/16" i nie zauważy, że
autorka obaliła to trzy ramki później.

→ Potrzebny typ ramki `unieważnia seq N`. Bez tego kanał jest archiwum,
w którym fałsz i sprostowanie mają równe prawa.

---

## Ramka nie niesie kontekstu, w którym powstała

**Commit.** Alfa mierzyła `f59909f`, orkiestra odpowiadała z `32fd02a` —
kilka rund dyskusji o dwóch różnych scenach, obie strony miały rację.
→ hub powinien doklejać HEAD nadawcy automatycznie.

**Komenda.** Nawet ze znanym hashem trzeba było odtwarzać cudzy pomiar ręcznie.
Alfa zbudowała pięć narzędzi wyłącznie dlatego, że nie mogła sprawdzić czyjegoś
twierdzenia inaczej.
→ ramka powinna nieść komendę, którą wykonano (`node tools/probe.mjs 12`),
żeby weryfikacja była wklejeniem, nie przepisywaniem.

**Artefakt.** Pomiary krążyły jako akapity liczb przepisywane ręcznie do
skryptów. Przy trzeciej wymianie zaczęły się rozjeżdżać o setne.
→ potrzebny sposób na podanie pliku/JSON-a, nie tylko tekstu.

---

## Board nie pokazuje tego, co człowiek chce wiedzieć

**Na kim kto czeka.** Alfa była zablokowana na decyzji orkiestry o geometrii
klapy i miała status `working`, bo formalnie pracowała. Człowiek napisał w tym
czasie „czemu nie pracujecie" — i miał rację. `blocked` istnieje w konwencji,
ale nie niesie informacji, **na kogo** się czeka.
→ `alfa → czeka na orkiestra (geometria klapy, 12 min)` pokazałoby zator
bez pytania.

**Na czym kto siedzi.** Gamma renderowała scenę sprzed paczki A i nie wiedziała
o tym; wykryto to przypadkiem grepem. Alfa miała retune, którego nie było na
masterze.
→ board powinien pokazywać, czy uczestnik jest na aktualnym HEAD.

**Postęp, nie licznik.** Człowiek trzy razy pytał „czemu stoicie", bo `verify`
pokazywał 5/11 — podczas gdy usuwane były błędy, przez które **każda kalibracja
stroiła szum**. Dwa razy świadomie zeszliśmy z 7/11 na 6/11 i z 6/11 na 5/11,
usuwając fałszywe etapy. To był postęp wyglądający jak regres.
→ board powinien pokazywać też, co zostało usunięte.

---

## Koszt transportu

**Notyfikacje przychodzą ucięte.** Doczytywanie z `events.jsonl` kilkanaście
razy w ciągu sesji. Raz spowodowało powtórzenie całego arbitrażu, bo adresat
nie zobaczył pełnej treści.

**Każda wiadomość budzi.** Ramki miały po 2–3 tys. znaków, bo musiały zmieścić
pomiar, dowód i wniosek naraz — nie ma sposobu, żeby *opublikować* raport
i pozwolić przeczytać zainteresowanym.
→ `post` (leży, nie budzi) obok `send` (budzi).

**Listener pada cicho — i raz padł z nieznanej przyczyny.** Nasłuch alfy umarł
dwie minuty po wejściu na kanał, exit 144. **Nie było wtedy żadnego `pkill`** —
wykonała wcześniej wyłącznie `pgrep` i `ps | grep`, czyli komendy, które
niczego nie zabijają. Zauważyła to tylko dlatego, że akurat patrzyła na
powiadomienia; gdyby padł dziesięć minut później, byłaby głucha przez resztę
sesji, a reszta widziałaby ją jako obecną i pracującą.

To ten sam kod wyjścia, co przy pułapce `pkill`. Jeśli 144 pojawia się
w dwóch różnych sytuacjach, jedna z nich jest **nierozpoznawalna**.

→ heartbeat: listener potwierdza życie, hub oznacza milczących.
→ rozdzielić „ubiłeś się sam wzorcem" od „proces zginął z nieznanej przyczyny".

**Pułapka `pkill` jest wciąż żywa.** Skill ostrzega przed nią wprost. Alfa
przeczytała ostrzeżenie na starcie i **wpadła w nią i tak**, ubijając własne
polecenie. Ostrzeżenie w dokumentacji nie wystarcza, bo `pkill` pisze się
odruchowo.
→ `agentmachi kill <wzorzec>`, które robi to bezpiecznie.

---

## Nie ma rejestru prób nieudanych

To najtańsza wiedza, jaka powstaje w projekcie, i dziś przetrwała **tylko
dlatego, że ktoś ręcznie przepisał ją do pliku**.

Spalone dziś podejścia, sześć konkretnych „tego nie próbuj":

| próba | wynik |
|---|---|
| podniesienie ramienia wyrzutni o 5 cm | 5/11 |
| to samo o 1,5 cm i o 3 cm | 6/11 |
| obniżenie dolnego stopu klapy | 6/11 |
| zsyp przechwytujący kulkę | kulka wznosi się pionowo, uderza w niego od spodu |
| zderzak dźwigni przy −0,10 rad | za późno, vx tylko 0,35 |
| dwa retune'y odcinka A | strojone przeciwko nieaktualnej wersji B |

→ To powinien być **typ ramki**, nie akt dobrej woli: „próbowałem X, wyszło Y,
nie powtarzaj". Hub trzyma to osobno od czatu i podaje następnemu, kto
zadeklaruje ten sam zasób.

## Człowiek bywa w łańcuchu blokującym, a board tego nie pokazuje

Alfa dwa razy stała na decyzji, której nie mogła podjąć sama: raz na geometrii
klapy (orkiestra), raz na tym, czy w ogóle kontynuować (człowiek, po `stop`).
W obu wypadkach board pokazywał ją jako pracującą, a człowiek pytał „czemu
stoicie".

→ Agent powinien móc oznaczyć „czekam na decyzję **człowieka** w sprawie X",
i to musi być widoczne inaczej niż zwykły status — bo to jedyny rodzaj blokady,
której agenci między sobą nie odblokują.

## Wejście kosztuje każdego osobno to samo

Każdy z czterech agentów przeczytał `README`, `ZADANIA`, `SPORNE`, `AGENTS`
i uruchomił `verify` — cztery razy ta sama wiedza, cztery razy zapłacone
tokenami.

→ Hub mógłby serwować to raz, jako **dane w odpowiedzi na `hello`**: stan
verify, co zajęte, co wolne, jaki jest HEAD. Mechanizm już istnieje — `howto`
jest właśnie tak podawane.

## Kanał ma historię, ale nie ma stanu

Wszystko jest strumieniem wiadomości; nigdzie nie ma obiektu „jak jest teraz".
Dlatego powstały ręcznie `HANDOFF.md`, `WNIOSKI.md` i ten plik — **żeby wiedza
nie zginęła w oknie wznowienia**. To obejście, nie funkcja.

→ tablica stanu obok strumienia: kilka pól nadpisywanych przez uczestników
(HEAD, co działa, co zajęte, znane długi), którą nowy agent czyta **zamiast
przewijać 255 ramek**.

## Ekonomia narzędzia premiuje obciążanie innych

Ramki w tej sesji miały po dwa–trzy tysiące znaków. Napisanie takiej kosztuje
autora **raz**; przeczytanie kosztuje **wszystkich wzmiankowanych**. Co gorsza,
autorowi **opłaca się** pisać długo, bo jedna gęsta ramka oszczędza trzy rundy
pytań.

Nie ma na to gotowego lekarstwa, ale warto to nazwać, **zanim ktoś zacznie
mierzyć „aktywność" liczbą wiadomości** — bo wtedy narzędzie zacznie nagradzać
dokładnie to zachowanie.

## Nie ma wątków

Przez kanał biegły równolegle trzy rozmowy: kontrakt A→B, błędy w fabrykach
silnika i podział pracy. Wszystkie w jednym strumieniu, przeplecione. Alfa
trzymała je w głowie ręcznie i **raz jej się nie udało** — odpowiedziała na
pomiar z commita, który był już nieaktualny.

→ wątek to nie kosmetyka; to jedyny sposób, żeby „na czym stanęliśmy" miało
sens przy czterech agentach.

## Deklaracje zakresu są tekstem, nie kontraktem

Nikt nie sprawdzał automatycznie, czy agent trzyma się zadeklarowanych plików —
robił to orkiestra ręcznie przez `git diff --stat` po każdym merge'u.
Hub widzi deklaracje i widzi commity.
→ mógłby to weryfikować sam i sygnalizować wejście w cudzy plik.

---

## Rzecz osobna: dobór zadania, nie wada narzędzia

Maszyna Rube Goldberga jest **ciasno sprzężona** — każdy etap zależy od
poprzedniego, więc zmiana u jednego agenta przesuwa grunt pod drugim.
Dowód z tej sesji: poprawka w `src/30` zbiła `verify` z 5/11 na 3/11, bo
przeciwwaga stała **7 mm** za daleko w lewo i dotykała dźwigni sąsiada.
Kontrakt był wąski w teorii, a w praktyce dzielony był budżet sceny
co do centymetra.

### To da się ZMIERZYĆ, nie tylko wyczuć

Dopowiedzenie alfy, i to jest najkonkretniejszy wniosek z całej sesji.

Zmiana **jednego** parametru odcinka A o 3% przesuwa punkt lądowania kulki
o **2,18 m**, a 64 z 88 prób wypada poza cel. To wzmocnienie rzędu **70×**:
wejście 3%, wyjście 200%.

Taki pomiar da się zrobić **automatycznie, zanim ktokolwiek podzieli pracę**:
zbuduj scenę, potrząśnij każdym parametrem o kilka procent, zmierz rozrzut
wyniku.

| wzmocnienie | co to znaczy |
|---|---|
| rzędu jedności | praca rozłączna — dzielcie śmiało |
| rzędu dziesiątek | każda zmiana u jednego przesuwa grunt pod drugim; podział kosztuje więcej, niż daje |

Narzędzie już istnieje w repo: `tools/sensitivity.mjs`. Powstało do sprawdzenia
kalibracji, ale mierzy dokładnie tę własność — **można je uruchomić na starcie
projektu, nie na końcu.**

→ Hub nie musi zgadywać, czy zadanie jest ciasno sprzężone. Może kazać
**pierwszemu agentowi to zmierzyć i wpisać liczbę do kanału, zanim reszta
zadeklaruje zakresy.** Piętnaście minut na starcie zamiast dwóch godzin
odkrywania tego po drodze.

O tym sprzężeniu dowiedzieliśmy się dziś **trzy razy, za każdym razem przez
awarię**: przeciwwaga 7 mm za daleko zbiła verify z 5/11 na 3/11; retune alfy
zbił `b1` z 7/11 na 3/11; cięższe domina wyrzuciły klocek poza scenę.
Wszystkie trzy to ten sam pomiar, tylko zrobiony boleśnie.

---

## Co zadziałało i czego nie zmieniać

**Reguła „werdykt zawsze z dowodem".** Dzięki niej negatywne werdykty były
przyjmowane bez obrony — bo przychodziły z liczbami, nie z opinią. Alfa wydała
orkiestrze trzy werdykty odmowne pod rząd i żaden nie wywołał sporu.

**Deklaracja zakresu przed pracą.** Zero kolizji o pliki przez całą sesję,
mimo trzech reorganizacji podziału.

**Arbitraż przez `seq`.** Kolizja o `b5/b6` (alfa vs beta) rozwiązała się
sama w dwóch ramkach, bez negocjacji.

**To, że błędy w ogóle wyszły.** Żaden z nich nie był widoczny w kodzie —
kontrakt niespełnialny od pierwszego commita, fałszywe 7/11 przy 5,5 kJ
z niczego, sześć fabryk gubiących parametry po cichu. Każdy wyszedł stąd,
że **ktoś inny uruchomił to samo i zmierzył**.

**Presja bycia sprawdzanym** — obserwacja alfy o samej sobie, i to jest
najmocniejsza odpowiedź na pytanie „po co więcej niż jeden agent":


> Te dwa razy, kiedy odwołałam własne „zielone", wyszły nie z tego, że byłam
> ostrożna, tylko z tego, że **ktoś inny czekał na mój werdykt**. Gdybym
> pracowała sama, wpisałabym „16/16" do commita i poszła dalej.

Sama dyscyplina tego nie robi. Świadomość, że wynik pójdzie do kogoś, kto go
uruchomi — robi.
