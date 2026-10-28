"""Autotest dell'eseguibile compilato:  Anonimizzatore --self-test [report.txt]

Non apre finestre. Controlla che nel pacchetto ci sia tutto: interprete Tcl/Tk,
lettura/scrittura Word e PDF, rilevamento e verifica. Esce con codice 0 se va bene.
Usato dalla build automatica (in modalità finestra su Windows non c'è console,
quindi il risultato va anche nel file indicato).
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

TESTO = ("Nell'interesse di Mario ROSSI (C.F. RSSMRA80A01L219X), residente in Torino, "
         "Via Garibaldi n. 12, email mario.rossi@example.it, tel. 347 123 4567.")


def _run(log) -> None:
    import tkinter

    tcl = tkinter.Tcl()                       # carica le librerie Tcl/Tk senza aprire finestre
    log(f"Tcl {tcl.eval('info patchlevel')}  ·  Tk {tkinter.TkVersion}")

    import pymupdf
    from docx import Document

    from . import pipeline
    from .model import Options

    log(f"PyMuPDF {pymupdf.VersionBind}  ·  Python {sys.version.split()[0]}  ·  {sys.platform}")
    with tempfile.TemporaryDirectory() as tmp:
        docx_in = os.path.join(tmp, "prova.docx")
        d = Document()
        d.add_paragraph(TESTO)
        d.save(docx_in)

        pdf_in = os.path.join(tmp, "prova.pdf")
        pdf = pymupdf.open()
        pdf.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 300), TESTO, fontsize=11)
        pdf.save(pdf_in)
        pdf.close()

        for path in (docx_in, pdf_in):
            src = pipeline.load(path)
            ents = pipeline.analyze(src, Options())
            rep = pipeline.export(src, ents, pipeline.default_output(path), Options())
            found = {e.category for e in ents}
            missing = {"PERSONA", "CF", "EMAIL", "TELEFONO", "INDIRIZZO"} - found
            if missing or rep.residual or rep.replaced < 5:
                raise RuntimeError(f"{os.path.basename(path)}: categorie mancanti {missing}, "
                                   f"residui {[e.text for e in rep.residual]}, sostituzioni {rep.replaced}")
            log(f"{os.path.splitext(path)[1]}: {rep.replaced} sostituzioni, verifica OK")


def main(argv: list[str]) -> int:
    report = argv[0] if argv else None
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg)

    try:
        _run(log)
        log("SELF-TEST OK")
        code = 0
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        log("SELF-TEST FALLITO")
        code = 1
    if report:
        with open(report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return code
