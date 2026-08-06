"""Token bucket na BAJTACH ramek — plot miedzy uczestnikiem a wspolnym
logiem. Czysta logika: zero I/O, zero sieci, zero zegara.

UCZCIWOSC DOWODOWA — przeczytaj, zanim uznasz to za lekcje z pracy.
Zalanie kanalu NIE wystapilo w zadnym dogfoodzie. To obrona przed
HIPOTEZA, nie przed pomiarem. Zmierzony jest wylacznie brak: hub mial
sufit JEDNEJ ramki (64 KiB) i keepalive, wiec uwierzytelniony uczestnik
mogl wyslac dowolnie WIELE ramek i nic go nie zatrzymywalo. Konstytucja
kaze projektowac na pomiar, nie na wyobraznie (bramka, pyt. 2), i ten
mechanizm jest swiadomym wyjatkiem od tej zasady: dotyczy fizyki, ktorej
agent nie zalatwi rozmowa — zalewany pisze do CUDZEGO logu, wiec ofiara
nie ma czym sie bronic.

BAJTY, nie ramki. Sufit `max_size` tnie jedna wielka ramke, ale lawina
malych kosztuje log tyle samo (ramka ma rozmiar minimalny, wiec liczba
ramek jest ograniczona przez bajty, a nie odwrotnie). Jedna jednostka
miary pokrywa oba ksztalty zalewu.

GRANICA (plot, nie pastuch). Ta klasa mowi WYLACZNIE, ile bajtow miesci
sie w drucie. Nie wie, kto pisze, o czym pisze ani ktora ramka jest
wazniejsza. Zero kolejkowania, zero priorytetow, zero "sprawiedliwego"
podzialu pasma — w chwili, gdy limiter zaczalby rozstrzygac KOLEJNOSC,
przestaje byc plotem i staje sie pastuchem, a to w tym projekcie jest
powod do odrzucenia zmiany.
"""


class FrameRateLimit:
    """Kubelek `burst_bytes` bajtow, uzupelniany `bytes_per_sec` na sekunde.

    Jedna instancja = jedna TOZSAMOSC (nick) — patrz `ChatServer._kubelki`
    i `_kubelek_tempa`. Do 2026-08-06 bylo per POLACZENIE i wygladalo na
    obrone, dopoki nie zmierzylismy trzeciej drogi zalewu: kazda ramka
    z osobnego socketu przeszla w calosci (30/30, zero odmow), bo kazde hello
    dostawalo swiezy, pelny kubelek. Tak wlasnie pisze `agentmachi send`.

    Zero zegara w logice (inwariant repo): czas przychodzi argumentem `now`,
    klasa nie wola `time.*` ani razu — dokladnie jak `RateLimiter.check`
    w `agentmachi/node.py`. Zrodlo `now` (u nas `time.monotonic`) jest
    decyzja wolajacego, a testy steruja nim wprost.

    KONTRAKT WOLAJACEGO: `burst_bytes` musi byc >= najwiekszej ramki, jaka
    moze przyjsc. Kubelek nigdy nie urosnie ponad `burst_bytes`, wiec ramka
    wieksza niz on nie przejdzie NIGDY — a `check` uczciwie zwracalaby za
    kazdym razem dodatni czas oczekiwania, czyli klient czekalby w kolko.
    Serwer pilnuje tego fail-fastem przy konstrukcji (`ChatServer.__init__`).
    """

    def __init__(self, bytes_per_sec, burst_bytes):
        # Kontrakt wejscia publicznej metody (inwariant repo): typ i sens
        # kazdego argumentu. Zero i wartosci ujemne ODRZUCAMY zamiast czytac
        # je jako "wylaczone": wylacznik wygladalby jak konfiguracja, a po
        # cichu kasowalby plot. Kto naprawde chce huba bez limitu, wpisuje
        # liczbe absurdalnie duza — i widzi ja w komendzie startu.
        for nazwa, wartosc in (("bytes_per_sec", bytes_per_sec),
                               ("burst_bytes", burst_bytes)):
            if isinstance(wartosc, bool) or not isinstance(wartosc,
                                                           (int, float)):
                raise TypeError(f"{nazwa} must be a number, got {wartosc!r}")
            if not wartosc > 0:
                raise ValueError(f"{nazwa} must be > 0, got {wartosc!r}")
        self.bytes_per_sec = float(bytes_per_sec)
        self.burst_bytes = float(burst_bytes)
        # Kubelek startuje PELNY: tozsamosc widziana pierwszy raz ma prawo od
        # razu wyslac zaleglosc (agent wchodzacy po przerwie wypycha to, czego
        # nie zdazyl). Uwaga: to dotyczy PIERWSZEGO kubelka danego nicka —
        # reconnect nie fabrykuje nowego, bo kubelek zyje przy tozsamosci
        # i przezywa rozlaczenie (patrz ChatServer._kubelek_tempa).
        self._poziom = float(burst_bytes)
        # None = jeszcze nie bylo ramki; pierwszy `check` ustawia punkt
        # odniesienia. Bez tego trzeba by wstrzykiwac czas juz w konstruktorze,
        # a wtedy odstep "konstrukcja -> pierwsza ramka" doliczalby sie do
        # kubelka, ktory i tak jest pelny.
        self._ostatnie = None

    def check(self, now, size):
        """Zwroc None, gdy ramka o `size` bajtach miesci sie w drucie, albo
        LICZBE SEKUND, po ktorej sie zmiesci.

        Ramka odrzucona NIE zabiera tokenow — nie zostala dostarczona, wiec
        nie ma za co placic. Uporczywosc lapie serwer (licznik odrzucen
        z rzedu), nie ten kubelek: karanie tokenami mieszaloby dwie rzeczy,
        z ktorych tylko jedna jest przepustowoscia.
        """
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise TypeError(f"now must be a number, got {now!r}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"size must be a non-negative int, got {size!r}")
        if self._ostatnie is None:
            self._ostatnie = now
        # `max(0.0, ...)`: cofniety czas nie kredytuje kubelka i nie karze.
        # Serwer podaje `time.monotonic`, wiec cofniecie nie powinno wystapic;
        # nie chcemy jednak, zeby WOLNY wybor zrodla czasu przez wolajacego
        # mogl wyprodukowac ujemne uzupelnienie i ujemny poziom.
        uplyw = max(0.0, now - self._ostatnie)
        self._ostatnie = now
        self._poziom = min(self.burst_bytes,
                           self._poziom + uplyw * self.bytes_per_sec)
        if size <= self._poziom:
            self._poziom -= size
            return None
        return (size - self._poziom) / self.bytes_per_sec
