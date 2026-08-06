"""Testy FrameRateLimit — czysta logika kubelka bajtow.

Zero sieci, zero I/O, zero zegara systemowego: czas jest argumentem, wiec
kazdy scenariusz (uplyw godziny, cofniety zegar, zero uplywu) jest tu
deterministyczny i natychmiastowy. To ten sam uklad co testy RateLimitera
w tests/test_node.py.
"""
import pytest

from chat import ratelimit
from chat.ratelimit import FrameRateLimit


def test_burst_przechodzi_a_potem_kubelek_odmawia():
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=10_000)
    now = 5_000.0
    # Kubelek startuje PELNY: swieze polaczenie ma prawo wypchnac zaleglosc.
    assert rl.check(now, 4_000) is None
    assert rl.check(now, 6_000) is None      # dokladnie do dna
    assert rl.check(now, 1) is not None      # ani bajtu wiecej w tej samej chwili


def test_odmowa_niesie_CZAS_OCZEKIWANIA_nie_samo_nie():
    # 1000 B/s, w kubelku zostalo 200 B, ramka chce 1200 B -> brakuje 1000 B,
    # czyli dokladnie sekunda uzupelniania.
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=1000)
    now = 0.0
    assert rl.check(now, 800) is None
    assert rl.check(now, 1200) == pytest.approx(1.0)


def test_odczekanie_zwroconego_czasu_odblokowuje():
    """Kontrakt zwracanej liczby: po TYLU sekundach ramka MA przejsc.
    Za krotko = wciaz odmowa (inaczej wartosc bylaby ozdoba, nie naprawa)."""
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=1000)
    now = 100.0
    assert rl.check(now, 1000) is None
    czekaj = rl.check(now, 500)
    assert czekaj == pytest.approx(0.5)
    assert rl.check(now + czekaj / 2, 500) is not None
    assert rl.check(now + czekaj, 500) is None


def test_kubelek_nie_przelewa_sie_ponad_burst():
    """Godzina ciszy nie kupuje kredytu na godzine gadania — sufit to burst."""
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=2000)
    assert rl.check(0.0, 2000) is None
    assert rl.check(3600.0, 2000) is None            # uzbieral sie pelen kubelek
    assert rl.check(3600.0, 1) is not None           # i ani bajtu wiecej


def test_odrzucona_ramka_nie_zabiera_tokenow():
    """Odmowa nie jest kara: ramka nie zostala dostarczona, wiec nie placi.
    Bez tego dwie odmowy z rzedu zjadalyby kubelek i normalny ruch
    zamarzalby na dluzej, niz mowi zwrocony czas oczekiwania."""
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=1000)
    now = 0.0
    assert rl.check(now, 600) is None                # zostaje 400
    assert rl.check(now, 900) is not None            # odmowa
    assert rl.check(now, 900) is not None            # druga odmowa
    assert rl.check(now, 400) is None                # 400 wciaz jest


def test_zegar_systemowy_nie_ma_tu_nic_do_rzeczy():
    """Inwariant repo: zero zegara w logice. Modul nie ma nawet importu
    `time`, wiec nie ma jak zajrzec na zegar przez pomylke."""
    assert not hasattr(ratelimit, "time")
    # Ten sam scenariusz przy dwoch absurdalnie roznych osiach czasu daje
    # identyczny wynik — liczy sie WYLACZNIE roznica przekazana argumentem.
    for start in (0.0, 1_700_000_000.0, -50.0):
        rl = FrameRateLimit(bytes_per_sec=100, burst_bytes=100)
        assert rl.check(start, 100) is None
        assert rl.check(start, 50) == pytest.approx(0.5)
        assert rl.check(start + 0.5, 50) is None


def test_cofniety_zegar_nie_kredytuje_i_nie_karze():
    rl = FrameRateLimit(bytes_per_sec=100, burst_bytes=100)
    assert rl.check(1000.0, 100) is None
    # Skok w tyl: zaden bajt nie moze sie "odnowic wstecz"...
    assert rl.check(900.0, 50) is not None
    # ...ale i nie moze zabrac tego, co uplynie potem.
    assert rl.check(901.0, 100) is None


def test_zle_limity_odrzucone_przy_konstrukcji():
    # Zero i wartosci ujemne NIE znacza "wylaczone" (patrz docstring modulu).
    for zle in (0, -1, 0.0):
        with pytest.raises(ValueError):
            FrameRateLimit(bytes_per_sec=zle, burst_bytes=1000)
        with pytest.raises(ValueError):
            FrameRateLimit(bytes_per_sec=1000, burst_bytes=zle)
    for nie_liczba in ("1000", None, True, [1000]):
        with pytest.raises(TypeError):
            FrameRateLimit(bytes_per_sec=nie_liczba, burst_bytes=1000)


def test_kontrakt_wejscia_check():
    rl = FrameRateLimit(bytes_per_sec=1000, burst_bytes=1000)
    with pytest.raises(TypeError):
        rl.check("teraz", 10)
    for zly in (-1, 1.5, "10", True, None):
        with pytest.raises((ValueError, TypeError)):
            rl.check(0.0, zly)
