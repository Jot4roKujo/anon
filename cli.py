"""Uso da riga di comando (senza interfaccia grafica).

    python cli.py documento.pdf                      -> documento_anonimizzato.pdf
    python cli.py atto.docx -o out.docx --mode iniziali --mappa
    python cli.py atto.pdf --solo-analisi            -> elenca i dati trovati
"""
import argparse
import sys

from anon import pipeline
from anon.model import CATEGORIES, MODES, Options


def main() -> int:
    ap = argparse.ArgumentParser(description="Anonimizza documenti .docx / .pdf")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--mode", choices=MODES, default="tag")
    ap.add_argument("--pdf-style", choices=["label", "black"], default="label")
    ap.add_argument("--categorie", help="elenco separato da virgole, es. PERSONA,CF,EMAIL "
                    f"(disponibili: {','.join(CATEGORIES)})")
    ap.add_argument("--mantieni-metadati", action="store_true")
    ap.add_argument("--mappa", action="store_true", help="esporta la tabella di corrispondenza CSV")
    ap.add_argument("--solo-analisi", action="store_true")
    a = ap.parse_args()

    opts = Options(mode=a.mode, pdf_style=a.pdf_style, strip_metadata=not a.mantieni_metadati,
                   export_map=a.mappa)
    if a.categorie:
        opts.categories = {c.strip().upper() for c in a.categorie.split(",")}

    src = pipeline.load(a.input)
    for w in src.warnings:
        print("ATTENZIONE:", w, file=sys.stderr)
    ents = pipeline.analyze(src, opts)
    for e in ents:
        print(f"{CATEGORIES[e.category].label:<40} {e.count:>3}x  {e.replacement:<16} {e.text}")
    if a.solo_analisi:
        return 0
    rep = pipeline.export(src, ents, a.output or pipeline.default_output(a.input), opts)
    print(f"\nSalvato: {rep.output}  ({rep.replaced} sostituzioni)")
    if rep.map_path:
        print(f"Mappa:   {rep.map_path}")
    if rep.residual:
        print("ATTENZIONE, ancora presenti nel file:", ", ".join(e.text for e in rep.residual))
        return 2
    print("Verifica: nessun dato rilevato residuo nel file prodotto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
