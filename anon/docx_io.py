"""Lettura e anonimizzazione di file Word (.docx).

Il testo di un paragrafo Word è spesso spezzato in più "run" (ogni cambio di
formattazione, correzione ortografica, revisione...). La sostituzione lavora
quindi sul testo concatenato del paragrafo e riporta le modifiche sui singoli
nodi <w:t>, mantenendo la formattazione del primo run coinvolto.

Vengono trattati: corpo, tabelle, caselle di testo, intestazioni/piè di pagina,
note, commenti, revisioni (testo eliminato), campi (es. HYPERLINK "mailto:..."),
destinazioni dei collegamenti ipertestuali, testo alternativo delle immagini e
metadati (autore, ultimo salvataggio, autori di commenti/revisioni).
"""
from __future__ import annotations

import re

from docx import Document
from docx.oxml.ns import qn

from .model import Matcher

W_P = qn("w:p")
TEXT_TAGS = (qn("w:t"), qn("w:delText"))
INSTR_TAG = qn("w:instrText")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

ANON_ATTRS = {"author": "Anonimo", "initials": "A", "userId": "anonimo", "providerId": "None"}


def _xml_parts(doc):
    for part in doc.part.package.iter_parts():
        el = getattr(part, "_element", None)
        if el is not None:
            yield part, el


def _own(p, tags):
    """Nodi testo che appartengono a questo paragrafo (non a paragrafi annidati)."""
    out = []
    for t in p.iter(*tags):
        anc = t.getparent()
        while anc is not None and anc.tag != W_P:
            anc = anc.getparent()
        if anc is p:
            out.append(t)
    return out


def read_text(path: str) -> str:
    doc = Document(path)
    lines = []
    for _, el in _xml_parts(doc):
        for p in el.iter(W_P):
            nodes = _own(p, TEXT_TAGS)
            if nodes:
                lines.append("".join(n.text or "" for n in nodes))
    return "\n\n".join(lines)


def _replace_in_nodes(nodes, matcher: Matcher) -> int:
    texts = [n.text or "" for n in nodes]
    full = "".join(texts)
    matches = list(matcher.finditer(full))
    if not matches:
        return 0
    starts, pos = [], 0
    for t in texts:
        starts.append(pos)
        pos += len(t)

    lens = [len(t) for t in texts]

    def locate(offset):
        # indice del nodo che contiene il carattere in posizione offset
        for i, (st, ln) in enumerate(zip(starts, lens)):
            if st <= offset < st + ln:
                return i
        return len(texts) - 1

    for s, e, ent in reversed(matches):
        i, j = locate(s), locate(e - 1)
        ls, le = s - starts[i], e - starts[j]
        if i == j:
            texts[i] = texts[i][:ls] + ent.replacement + texts[i][le:]
        else:
            texts[i] = texts[i][:ls] + ent.replacement
            for k in range(i + 1, j):
                texts[k] = ""
            texts[j] = texts[j][le:]
    for n, t in zip(nodes, texts):
        if n.text != t:
            n.text = t
            if t != t.strip():
                n.set(XML_SPACE, "preserve")
    return len(matches)


def anonymize(src: str, dst: str, entities, strip_metadata: bool = True) -> int:
    doc = Document(src)
    matcher = Matcher(entities)
    total = 0
    for part, el in _xml_parts(doc):
        for p in el.iter(W_P):
            total += _replace_in_nodes(_own(p, TEXT_TAGS), matcher)
            instr = _own(p, (INSTR_TAG,))
            if instr:
                _replace_in_nodes(instr, matcher)
        # testo alternativo / titolo delle immagini
        for node in el.iter(qn("wp:docPr")):
            for attr in ("descr", "title", "name"):
                if node.get(attr):
                    node.set(attr, matcher.sub(node.get(attr))[0])
        # destinazioni dei collegamenti (mailto:, http://...)
        for rel in part.rels.values():
            if rel.is_external and isinstance(getattr(rel, "_target", None), str):
                new, n = matcher.sub(rel._target)
                if n:
                    rel._target = new if not new.startswith("mailto:[") else "mailto:anonimo@example.invalid"
        if strip_metadata:
            for node in el.iter():
                for k in list(node.attrib):
                    local = k.rsplit("}", 1)[-1]
                    if local in ANON_ATTRS and (k.startswith("{") or local == "author"):
                        node.set(k, ANON_ATTRS[local])
    if strip_metadata:
        cp = doc.core_properties
        for f in ("author", "last_modified_by", "title", "subject", "keywords", "comments",
                  "category", "content_status", "identifier", "version"):
            try:
                setattr(cp, f, "")
            except Exception:
                pass
        for part in doc.part.package.iter_parts():
            if str(part.partname).endswith("/docProps/app.xml"):
                el = getattr(part, "_element", None)
                if el is not None:
                    for node in el.iter():
                        if re.sub(r"^\{.*\}", "", node.tag) in ("Company", "Manager", "HyperlinkBase"):
                            node.text = ""
                elif hasattr(part, "_blob"):
                    part._blob = re.sub(rb"<(Company|Manager|HyperlinkBase)>[^<]*</\1>",
                                        rb"<\1></\1>", part._blob)
    doc.save(dst)
    return total
