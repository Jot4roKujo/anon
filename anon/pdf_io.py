"""Lettura e redazione di PDF con PyMuPDF.

La redazione è "vera": il testo sotto i riquadri viene rimosso dal file (non solo
coperto), le porzioni di immagine sottostanti vengono cancellate, e al posto del
dato compare l'etichetta di sostituzione (o un riquadro nero).

Le entità vengono cercate parola per parola, così un nome spezzato su due righe
("Anna / Maria Rossi") viene comunque trovato.
"""
from __future__ import annotations

import re

import pymupdf

from .model import Entity, Matcher, clean

EDGE = " \t\n,;:.!?\"'«»“”‘’()[]{}<>–-"
CORE_STRIP = EDGE


def _core(s: str) -> str:
    return clean(s).strip(CORE_STRIP).casefold()


def read_text(path: str) -> tuple[str, int, int]:
    """Restituisce (testo, numero pagine, pagine senza testo)."""
    doc = pymupdf.open(path)
    parts, empty = [], 0
    for page in doc:
        t = page.get_text()
        if not clean(t).strip():
            empty += 1
        parts.append(t)
    n = doc.page_count
    doc.close()
    return "\n".join(parts), n, empty


def _tok_match(word: str, tok: str, pos: str, strict: bool) -> bool:
    wc, tc = _core(word), _core(tok)
    if not tc:                                     # token di sola punteggiatura ("-")
        return clean(word).strip() in ("-", "–", "—", ",", tok.strip())
    if pos == "only":
        if wc == tc:
            return True
        # parole composte: "Rossi-Bianchi", "dell'Avv", "Rossi/Bianchi"
        parts = re.split(r"[-/'’.@]", wc)
        return tc in parts if strict else tc in wc
    if pos == "first":
        return wc.endswith(tc)
    if pos == "last":
        return wc.startswith(tc)
    return wc == tc


def _upper_initial(s: str) -> bool:
    for ch in s:
        if ch.isalpha():
            return ch.isupper()
    return True


def _find_on_page(page, words, used, ent: Entity):
    toks = ent.text.split()
    n = len(toks)
    strict = ent.category in ("PERSONA", "SOCIETA", "MANUALE")
    hits = []
    i = 0
    while i <= len(words) - n:
        ok = True
        for k, tok in enumerate(toks):
            pos = "only" if n == 1 else "first" if k == 0 else "last" if k == n - 1 else "middle"
            if (i + k) in used or not _tok_match(words[i + k][4], tok, pos, strict):
                ok = False
                break
        if ok and ent.category == "PERSONA" and not _upper_initial(clean(words[i][4]).strip(EDGE)):
            ok = False
        if ok:
            rects = []
            for k, tok in enumerate(toks):
                w = words[i + k]
                wrect = pymupdf.Rect(w[:4])
                rect = wrect
                if _core(w[4]) != _core(tok) or clean(w[4]).strip() != tok:
                    clip = wrect + (-1, -1, 1, 1)
                    found = page.search_for(tok, clip=clip) or page.search_for(tok.strip(EDGE) or tok, clip=clip)
                    if found:
                        rect = found[0]
                rects.append((w[5], w[6], rect))
                if _core(w[4]) == _core(tok):          # parola intera: non riutilizzabile
                    used.add(i + k)
            hits.append(rects)
            i += n
        else:
            i += 1
    return hits


def _merge_line_rects(rects):
    """Unisce i rettangoli consecutivi della stessa riga."""
    merged = []
    for block, line, r in rects:
        if merged and merged[-1][0] == (block, line):
            merged[-1][1] |= r
        else:
            merged.append([(block, line), pymupdf.Rect(r)])
    return [r for _, r in merged]


def _fit_fontsize(text: str, rect: pymupdf.Rect) -> float:
    fs = min(rect.height * 0.8, 11)
    width = pymupdf.get_text_length(text, fontname="helv", fontsize=fs)
    if width > rect.width - 1:
        fs *= (rect.width - 1) / width
    return max(fs, 3.5)


def anonymize(src: str, dst: str, entities: list[Entity], style: str = "label",
              strip_metadata: bool = True) -> int:
    doc = pymupdf.open(src)
    active = sorted((e for e in entities if e.enabled), key=lambda e: len(e.text), reverse=True)
    matcher = Matcher(entities)
    total = 0
    for page in doc:
        words = [w for w in page.get_text("words") if clean(w[4]).strip()]
        used: set[int] = set()
        for ent in active:
            for rects in _find_on_page(page, words, used, ent):
                total += 1
                for idx, r in enumerate(_merge_line_rects(rects)):
                    label = ent.replacement if idx == 0 and style == "label" else ""
                    if style == "black":
                        page.add_redact_annot(r, fill=(0, 0, 0))
                    elif label:
                        # il riquadro si allarga se l'etichetta è più lunga del dato originale
                        page.add_redact_annot(r, text=label, fontname="helv",
                                              fontsize=_fit_fontsize(label, r),
                                              fill=(0.9, 0.9, 0.9), text_color=(0, 0, 0),
                                              align=pymupdf.TEXT_ALIGN_LEFT)
                    else:
                        page.add_redact_annot(r, fill=(0.9, 0.9, 0.9))
        # collegamenti che contengono dati (mailto:, url personali)
        for link in page.get_links():
            uri = link.get("uri") or ""
            if uri and any(True for _ in matcher.finditer(uri)):
                page.delete_link(link)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if strip_metadata:
        doc.scrub(metadata=True, xml_metadata=True, attached_files=True, embedded_files=True,
                  thumbnails=True, javascript=True, hidden_text=False, remove_links=False,
                  reset_fields=False, reset_responses=True, clean_pages=False, redactions=False)
        doc.set_metadata({})
    doc.save(dst, garbage=4, deflate=True, clean=True)
    doc.close()
    return total
