# Wyjscie CLI musi byc UTF-8-safe niezaleznie od codepage systemu. Bez tego
# _print_event (send.py) pada na UnicodeEncodeError i UBIJA listener na Windows
# (polski cp1250). Zlapane na Windows Bartka: `agentmachi listen` czytal resync
# i wychodzil z EXIT 1 na U+FF82. Test odtwarza dokladnie ten znak.
import io

from agentmachi.cli import _force_utf8_output


def test_reconfigure_realnego_strumienia_na_utf8():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1250")  # jak polski Windows
    _force_utf8_output(stream)
    assert stream.encoding.lower() == "utf-8"
    assert stream.errors == "replace"


def test_znak_spoza_cp1250_nie_wywraca_zapisu():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1250")
    _force_utf8_output(stream)
    stream.write("zostaﾂlej")   # U+FF82 — dokladnie ten z crashu codeksa
    stream.flush()
    assert "ﾂ".encode("utf-8") in raw.getvalue()   # zero wyjatku, poprawny UTF-8


def test_noop_gdy_strumien_bez_reconfigure():
    # StringIO nie ma reconfigure -> guard lapie AttributeError, zero wyjatku
    _force_utf8_output(io.StringIO())


def test_wiele_strumieni_naraz():
    a = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    b = io.TextIOWrapper(io.BytesIO(), encoding="latin-1")
    _force_utf8_output(a, b)
    assert a.encoding.lower() == "utf-8"
    assert b.encoding.lower() == "utf-8"
