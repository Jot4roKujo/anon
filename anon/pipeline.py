"""Facciata unica usata da GUI e CLI: carica, analizza, esporta, verifica."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

from . import docx_io, pdf_io
from .detector import detect
from .model import CATEGORIES, Entity, Matcher, Options, assign_replacements, clean, recount

SUPPORTED = (".docx", ".pdf")


@dataclass
class Source:
    path: str
    kind: str
    text: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class Report:
    output: str
    replaced: int
    residual: list[Entity]
    map_path: str | None = None


def load(path: str) -> Source:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return Source(path, "docx", clean(docx_io.read_text(path)))
    if ext == ".pdf":
        text, pages, empty = pdf_io.read_text(path)
        src = Source(path, "pdf", clean(text))
        if empty == pages:
            src.warnings.append("Il PDF non contiene testo selezionabile (probabilmente è una "
                                "scansione): serve prima un passaggio OCR.")
        elif empty:
            src.warnings.append(f"{empty} pagine su {pages} non contengono testo (immagini/scansioni): "
                                "il loro contenuto NON verrà anonimizzato.")
        return src
    if ext == ".doc":
        raise ValueError("Il formato .doc (Word 97-2003) non è supportato: salvalo come .docx da Word.")
    raise ValueError(f"Formato non supportato: {ext}. Usa .docx o .pdf.")


def analyze(src: Source, opts: Options) -> list[Entity]:
    ents = detect(src.text, opts)
    assign_replacements(ents, opts.mode)
    return ents


def refresh(src: Source, entities: list[Entity], mode: str) -> None:
    """Da chiamare dopo modifiche manuali (attiva/disattiva, aggiungi, rimuovi)."""
    recount(entities, src.text)
    assign_replacements(entities, mode)


def preview(src: Source, entities: list[Entity]) -> str:
    return Matcher(entities).sub(src.text)[0]


def default_output(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}_anonimizzato{ext}"


def export(src: Source, entities: list[Entity], out_path: str, opts: Options) -> Report:
    if os.path.abspath(out_path) == os.path.abspath(src.path):
        raise ValueError("Il file di destinazione deve essere diverso dall'originale.")
    if src.kind == "docx":
        n = docx_io.anonymize(src.path, out_path, entities, opts.strip_metadata)
    else:
        n = pdf_io.anonymize(src.path, out_path, entities, opts.pdf_style, opts.strip_metadata)
    residual = verify(out_path, entities)
    map_path = None
    if opts.export_map:
        map_path = os.path.splitext(out_path)[0] + "_mappa.csv"
        write_map(map_path, entities)
    return Report(out_path, n, residual, map_path)


def verify(out_path: str, entities: list[Entity]) -> list[Entity]:
    """Rilegge il file prodotto e restituisce le entità ancora presenti."""
    text = clean(load(out_path).text)
    left: dict[str, Entity] = {}
    for _, _, ent in Matcher(entities).finditer(text):
        # un'etichetta che contiene il dato stesso (es. sostituzione personalizzata) non conta
        if ent.replacement and ent.text.casefold() in ent.replacement.casefold():
            continue
        left[ent.key] = ent
    return list(left.values())


def write_map(path: str, entities: list[Entity]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Categoria", "Originale", "Sostituzione", "Occorrenze"])
        for e in sorted(entities, key=lambda x: x.first_pos):
            if e.enabled:
                w.writerow([CATEGORIES[e.category].label, e.text, e.replacement, e.count])
