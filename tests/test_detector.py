"""Test su dati inventati.  Esegui:  python -m pytest tests   (oppure  python tests/test_detector.py)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anon.detector import detect, valid_iban, valid_piva  # noqa: E402
from anon.model import Matcher, Options, assign_replacements  # noqa: E402

TESTO = """Avv. Mario Rossi
Via Garibaldi n. 12 - 10121 - TORINO
mario.rossi@pec.example.it - Tel. (+39) 011.123.45.67 - cell. 347 123 4567

Nell'interesse di Giulia BIANCHI (C.F. BNCGLI80A41L219X) nata a Torino il 01.01.1980,
residente in Torino, Corso Francia 200, rappresentata dall'Avv. Mario Rossi.

CONTRO Alfa Servizi S.r.l. (P.IVA 01234567897), in persona del legale rappresentante.

1. In data 03/10/23 la signora Bianchi, insieme ai signori Luca Verdi, Anna Neri e
Carlo Esposito, prenotava il volo AZ1234 (codice prenotazione X7K9QP).
Il rimborso andrà su IBAN IT60 X054 2811 1010 0000 0123 456.
Cass. 3468/1991; Tribunale di Torino, sentenza n. 1234/2020. Importo € 3.696,70.
Testimoni: Luca Verdi, Torino; Anna Neri, Torino. Copia a M. Rossi.
"""


def found(cats=None):
    o = Options()
    if cats:
        o.categories = set(cats)
    o.categories.add("SOCIETA")
    ents = detect(TESTO, o)
    return {e.text: e for e in ents}


def test_validatori():
    assert valid_piva("01234567897")
    assert not valid_piva("01234567890")
    assert valid_iban("IT60 X054 2811 1010 0000 0123 456")
    assert not valid_iban("IT61 X054 2811 1010 0000 0123 456")


def test_dati_strutturati():
    f = found()
    assert f["BNCGLI80A41L219X"].category == "CF"
    assert f["01234567897"].category == "PIVA"
    assert f["mario.rossi@pec.example.it"].category == "EMAIL"
    assert f["(+39) 011.123.45.67"].category == "TELEFONO"
    assert f["347 123 4567"].category == "TELEFONO"
    assert f["01.01.1980"].category == "DATA_NASCITA"
    assert f["Via Garibaldi n. 12 - 10121 - TORINO"].category == "INDIRIZZO"
    assert f["Corso Francia 200"].category == "INDIRIZZO"
    assert f["X7K9QP"].category == "CODICE"
    assert f["IT60 X054 2811 1010 0000 0123 456"].category == "IBAN"
    assert f["Alfa Servizi S.r.l."].category == "SOCIETA"


def test_nessun_falso_positivo():
    f = found()
    for txt in ("03/10/23", "3468/1991", "1234/2020", "AZ1234", "3.696,70", "Torino", "Tribunale"):
        assert txt not in f, txt


def test_persone_e_propagazione():
    f = found()
    for nome in ("Mario Rossi", "Giulia BIANCHI", "Luca Verdi", "Anna Neri", "Carlo Esposito"):
        assert f[nome].category == "PERSONA", nome
    # cognome da solo e iniziale puntata -> stessa persona
    assert f["Bianchi"].group == f["Giulia BIANCHI"].group
    assert f["M. Rossi"].group == f["Mario Rossi"].group


def test_sostituzione_coerente():
    o = Options()
    ents = detect(TESTO, o)
    assign_replacements(ents, "tag")
    out, n = Matcher(ents).sub(TESTO)
    assert "Rossi" not in out and "BIANCHI" not in out and "Bianchi" not in out
    assert out.count("[PERSONA_1]") >= 2
    assert "3468/1991" in out and "AZ1234" in out
    assign_replacements(ents, "iniziali")
    out, _ = Matcher(ents).sub(TESTO)
    assert "G.B." in out and "M.R." in out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
