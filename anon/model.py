"""Modello dati: categorie, entità, matcher e calcolo delle sostituzioni."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_HS = r"[ \t\r\f\v\u00a0\u200b\u200c\u200d\u2060\ufeff]"
# spazi tra le parole di un'entità: al massimo un a capo (riga vuota = paragrafo diverso)
WS = rf"(?:{_HS}*\n{_HS}*|{_HS}+)"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    tag: str
    default: bool
    color: str


CATEGORIES: dict[str, Category] = {c.key: c for c in [
    Category("PERSONA", "Persone", "PERSONA", True, "#f2a65a"),
    Category("CF", "Codici fiscali", "CF", True, "#e06c75"),
    Category("PIVA", "Partite IVA", "PIVA", True, "#d19a66"),
    Category("EMAIL", "Email / PEC", "EMAIL", True, "#61afef"),
    Category("TELEFONO", "Telefoni / Fax", "TELEFONO", True, "#56b6c2"),
    Category("INDIRIZZO", "Indirizzi", "INDIRIZZO", True, "#98c379"),
    Category("IBAN", "IBAN", "IBAN", True, "#c678dd"),
    Category("DATA_NASCITA", "Date di nascita", "DATA_NASCITA", True, "#e5c07b"),
    Category("CODICE", "Codici pratica / prenotazione / targhe", "CODICE", True, "#be5046"),
    Category("SOCIETA", "Società / enti", "SOCIETA", False, "#7f9fbf"),
    Category("URL", "Siti web", "URL", False, "#8fa1b3"),
    Category("MANUALE", "Aggiunti a mano", "DATO", True, "#ff79c6"),
]}

MODES = {
    "tag": "Etichette coerenti  ([PERSONA_1], [CF_1]…)",
    "iniziali": "Iniziali per le persone (J.S.), [omissis] per il resto",
    "omissis": "Tutto come [omissis]",
}


def clean(text: str) -> str:
    """Rimuove caratteri invisibili e normalizza gli spazi non separabili."""
    return text.translate(ZERO_WIDTH).replace(" ", " ")


def norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", clean(text)).strip().casefold()


@dataclass
class Entity:
    text: str
    category: str
    group: str = ""
    enabled: bool = True
    replacement: str = ""
    custom_replacement: bool = False
    source: str = "auto"
    count: int = 0
    first_pos: int = 10**9

    def __post_init__(self):
        self.text = re.sub(r"\s+", " ", clean(self.text)).strip()
        if not self.group:
            self.group = norm_key(self.text)

    @property
    def key(self) -> str:
        return norm_key(self.text)


def entity_pattern(text: str) -> str:
    parts = text.split()
    body = WS.join(re.escape(p) for p in parts)
    pre = r"(?<!\w)" if re.match(r"\w", text) else ""
    post = r"(?!\w)" if re.search(r"\w$", text) else ""
    return pre + body + post


def _upper_initial(s: str) -> bool:
    for ch in s:
        if ch.isalpha():
            return ch.isupper()
    return True


class Matcher:
    """Trova nel testo tutte le occorrenze delle entità attive (la più lunga vince)."""

    def __init__(self, entities: list[Entity]):
        active = sorted((e for e in entities if e.enabled and e.text),
                        key=lambda e: len(e.text), reverse=True)
        self.by_key: dict[str, Entity] = {}
        for e in active:
            self.by_key.setdefault(e.key, e)
        pats = [entity_pattern(e.text) for e in self.by_key.values()]
        self.rx = re.compile("|".join(pats), re.IGNORECASE) if pats else None

    def finditer(self, text: str):
        if not self.rx:
            return
        for m in self.rx.finditer(text):
            ent = self.by_key.get(norm_key(m.group()))
            if ent is None:
                continue
            # i nomi di persona vanno sostituiti solo se scritti con l'iniziale maiuscola
            if ent.category == "PERSONA" and not _upper_initial(m.group()):
                continue
            yield m.start(), m.end(), ent

    def sub(self, text: str) -> tuple[str, int]:
        out, last, n = [], 0, 0
        for s, e, ent in self.finditer(text):
            out.append(text[last:s])
            out.append(ent.replacement)
            last, n = e, n + 1
        out.append(text[last:])
        return "".join(out), n


def recount(entities: list[Entity], text: str) -> None:
    """Aggiorna occorrenze e posizione della prima occorrenza di ogni entità."""
    for e in entities:
        e.count, e.first_pos = 0, 10**9
    for s, _, ent in Matcher(entities).finditer(text):
        ent.count += 1
        ent.first_pos = min(ent.first_pos, s)


def initials(text: str) -> str:
    out = []
    for tok in text.split():
        letters = [c for c in tok if c.isalpha()]
        if letters:
            out.append(letters[0].upper() + ".")
    return "".join(out) or "[omissis]"


def assign_replacements(entities: list[Entity], mode: str) -> None:
    counters: dict[str, int] = {}
    labels: dict[tuple[str, str], str] = {}
    for e in sorted(entities, key=lambda x: (x.first_pos, -len(x.text))):
        if e.custom_replacement:
            continue
        if mode == "omissis":
            e.replacement = "[omissis]"
        elif mode == "iniziali":
            e.replacement = initials(e.text) if e.category == "PERSONA" else "[omissis]"
        else:
            gk = (e.category, e.group)
            if gk not in labels:
                tag = CATEGORIES[e.category].tag
                counters[tag] = counters.get(tag, 0) + 1
                labels[gk] = f"[{tag}_{counters[tag]}]"
            e.replacement = labels[gk]


@dataclass
class Options:
    categories: set[str] = field(default_factory=lambda: {k for k, c in CATEGORIES.items() if c.default})
    mode: str = "tag"
    pdf_style: str = "label"          # "label" = riquadro chiaro con etichetta, "black" = riquadro nero
    strip_metadata: bool = True
    export_map: bool = False
    whitelist: set[str] = field(default_factory=set)      # chiavi normalizzate da non anonimizzare mai
    extra_names: set[str] = field(default_factory=set)    # nomi propri aggiuntivi
    always_terms: list[tuple[str, str]] = field(default_factory=list)  # (testo, categoria) da anonimizzare sempre
