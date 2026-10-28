"""Rilevamento automatico dei dati personali in testi giuridici italiani.

Approccio a regole (nessun modello da scaricare, funziona offline e si impacchetta
facilmente con PyInstaller):
  * pattern con validazione (codice fiscale, P.IVA con cifra di controllo, IBAN mod-97, ...)
  * pattern di contesto ("nato a ... il", "Riferimento cliente", "P.IVA", ...)
  * euristica per i nomi di persona (sequenze maiuscole con nome proprio o titolo)
  * propagazione: un valore trovato una volta viene sostituito ovunque compaia,
    e il cognome di una persona viene sostituito anche quando compare da solo.
"""
from __future__ import annotations

import re

from .lexicon import CITIES, FIRST_NAMES, PARTICLES, STOPWORDS, TITLE_WORDS
from .model import CATEGORIES, Entity, Options, clean, norm_key, recount

# --------------------------------------------------------------------------- pattern

UP = "A-ZÀ-ÖØ-Ý"
LO = "a-zà-öø-ÿß"

RX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
RX_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.I)

RX_CF = re.compile(
    r"(?<![A-Z0-9])[A-Z]{3} ?[A-Z]{3} ?[0-9LMNPQRSTUV]{2} ?[ABCDEHLMPRST][0-9LMNPQRSTUV]{2} ?"
    r"[A-Z][0-9LMNPQRSTUV]{3} ?[A-Z](?![A-Z0-9])")

RX_PIVA_CTX = re.compile(
    r"(?i:\bp\.?\s?iva|\bpartita\s+iva|\bvat(?:\s+(?:no\.?|number|id))?|\bc\.?\s?f\.?\s*/\s*p\.?\s?iva)"
    r"\s*[:.]?\s*(?:(?i:n)\.?\s*)?((?:[A-Z]{2}\s?)?[0-9][0-9A-Z]{7,13})")
RX_PIVA_BARE = re.compile(r"(?<![\w/.,-])(?:IT\s?)?(\d{11})(?![\w/])")

RX_IBAN = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?(?![A-Z0-9])")

RX_PHONE = re.compile(
    r"(?:(?<![\d+\-/,])(?:\(\s?\+\d{1,3}\s?\)|(?<!\w)\+\d{1,3}|(?<!\w)00\d{2})[ .\-]*\d(?:[ .\-]?\d){5,12}"
    r"|(?<![\w+\-/.,])(?:0|3)\d(?:[ .\-]?\d){5,11})(?!\w)")
RX_DATE_LIKE = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")

MONTHS = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
RX_BIRTH = re.compile(
    r"(?i:\bnat[oa]\b|\bnata/o\b|\bdata\s+di\s+nascita\b|\bd\.n\.|\bborn\b)[^;]{0,45}?"
    r"(?i:\bil\b|\bon\b|:)\s*"
    rf"(\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}|\d{{1,2}}\s+(?i:{MONTHS})\s+\d{{4}})")

STREET = (r"(?i:via|viale|v\.le|piazza|p\.zza|piazzale|p\.le|corso|c\.so|largo|vicolo|vico|strada|"
          r"str\.|contrada|c\.da|località|loc\.|borgo|lungomare|lungotevere|galleria|salita|"
          r"calle|fondamenta|frazione|fraz\.)")
RX_ADDR_IT = re.compile(
    rf"(?<!\w){STREET}\s+[{UP}0-9][\w'’.]*(?:\s+[\w'’.]+){{0,5}}?,?\s+"
    r"(?:(?i:n|nr|n°|num|civ)\.?\s*)?\d{1,4}(?:\s?/\s?[A-Za-z0-9]|[A-Za-z](?!\w))?(?![\w/])"
    rf"(?:\s*[-–,]\s*\d{{5}}(?:\s*[-–,]?\s*[{UP}][\w'’]+(?:\s*\([A-Z]{{2}}\))?)?)?")
RX_ADDR_FOREIGN = re.compile(
    rf"(?<!\w)[{UP}][{LO}]+(?i:straat|weg|kade|gracht|plein|laan|strasse|straße|gasse|platz|allee)"
    r"\s+\d{1,4}[a-zA-Z]?(?:,?\s+\d{4}\s?[A-Z]{2}(?![A-Za-z]))?"
    rf"|(?<!\w)\d{{1,5}}\s+(?:[{UP}][{LO}]+\s+){{1,3}}(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Boulevard|Blvd\.|Drive|Square)"
    rf"|(?<!\w)\d{{1,4}},?\s+(?i:rue|avenue|boulevard|place|chemin)\s+(?:[\w'’-]+\s+){{0,4}}?[{UP}][\w'’-]+")

RX_CODE_CTX = re.compile(
    r"(?i:\briferimento\s+cliente|\bn(?:umero|\.)\s*(?:di\s+|del(?:la)?\s+)?(?:prenotazione|pratica|ordine|"
    r"cliente|biglietto|polizza|contratto|fattura|sinistro|protocollo|matricola|tessera|e-ticket)|"
    r"\bcodice\s+(?:prenotazione|cliente|pratica|utente)|\bpnr\b|\bbooking\s+(?:reference|code|number)|"
    r"\bsigla\b|\bunder\b|\bticket\s+(?:number|no\.?)|\btarga\b)\s*[:n.°]*\s*([A-Z0-9][A-Z0-9\-/]{4,})")
RX_PNR = re.compile(r"(?<![A-Za-z0-9])(?=[A-Z0-9]{6}(?![A-Za-z0-9]))(?=[A-Z]*\d)(?=\d*[A-Z])[A-Z0-9]{6}(?![A-Za-z0-9])")
RX_FLIGHT = re.compile(r"[A-Z]{2}\d{3,4}|[A-Z]\d{4,5}|\d[A-Z]\d{3,4}")
RX_ETICKET = re.compile(r"(?<![\d-])\d{3}[ -]?\d{10}(?![\d-])")
RX_PLATE = re.compile(r"(?<![A-Z0-9])[A-Z]{2} ?\d{3} ?[A-Z]{2}(?![A-Za-z0-9])")

LEGAL_FORMS = (r"S\.p\.A\.|S\.r\.l\.s?\.?|S\.n\.c\.|S\.a\.s\.|S\.s\.|S\.c\.a\.r\.l\.|B\.V\.|N\.V\.|GmbH|AG|"
               r"Ltd\.?|LLC|Inc\.|S\.A\.|SpA|Srl|SRL|SPA|Onlus|ONLUS")
RX_COMPANY = re.compile(
    rf"((?:[{UP}0-9][\w&.'’-]*[ \t]+){{0,3}}[{UP}0-9][\w&.'’-]*?)[ \t]*,?[ \t]+({LEGAL_FORMS})(?![\w])")

NAME_TOKEN = (rf"(?:[{UP}][{LO}]+(?:['’][{UP}][{LO}]+)?|[{UP}]['’][{UP}][{LO}]+|"
              rf"[{UP}]{{2,}}(?:['’][{UP}]+)?)")
RX_NAME_SEQ = re.compile(rf"{NAME_TOKEN}(?:(?:[ \t]*\n[ \t]*|[ \t]+){NAME_TOKEN})*")
RX_NAME_TOKEN = re.compile(NAME_TOKEN)
RX_TITLE_BEFORE = re.compile(
    r"(?i:\b(?:avv|avvocato|avvocatessa|dott|dott\.ssa|dottor|dottoressa|dr|prof|prof\.ssa|ing|arch|"
    r"geom|rag|sig|sig\.ra|sig\.na|sigg|sig\.ri|signor|signora|signorina|signori|mr|mrs|ms|miss|"
    r"notaio|giudice\s+estensore|egr\.?\s*sig|gent\.m[oa])\.?)\s*$")
# inneschi "deboli": la sequenza successiva è un nome se ha almeno 2 parole
RX_TRIGGER_BEFORE = re.compile(
    r"(?i:\b(?:testimone|teste|testi|sottoscritt[oa]|nell['’]interesse\s+di|in\s+favore\s+di|"
    r"a\s+favore\s+di|in\s+persona\s+di|nei\s+confronti\s+di|contro|vs\.?|c/)\s*:?)\s*$")
RX_LIST_SEP = re.compile(r"\s*(?:,|;|\be\b|\bed\b)\s*")


# --------------------------------------------------------------------------- validatori

def valid_piva(num: str) -> bool:
    if not re.fullmatch(r"\d{11}", num) or num == "0" * 11:
        return False
    s = 0
    for i, ch in enumerate(num[:10]):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return (10 - s % 10) % 10 == int(num[10])


def valid_iban(raw: str) -> bool:
    s = raw.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    s = s[4:] + s[:4]
    try:
        return int("".join(str(int(c, 36)) for c in s)) % 97 == 1
    except ValueError:
        return False


# --------------------------------------------------------------------------- nomi

def _person_candidates(text: str, first_names: set[str]):
    """Restituisce (start, end, titled) per ogni nome di persona plausibile."""
    results = []
    for seq in RX_NAME_SEQ.finditer(text):
        toks = list(RX_NAME_TOKEN.finditer(seq.group()))
        base = seq.start()
        chunks, cur, titled_next = [], [], False
        chunk_titled = []
        for i, t in enumerate(toks):
            w = t.group().casefold()
            nxt = toks[i + 1].group() if i + 1 < len(toks) else ""
            is_particle = (w in PARTICLES and cur and nxt and t.group()[0].isupper()
                           and nxt.casefold() not in STOPWORDS)
            if w in TITLE_WORDS:
                if cur:
                    chunks.append(cur); chunk_titled.append(titled_next)
                cur, titled_next = [], True
            elif w in STOPWORDS and not is_particle:
                if cur:
                    chunks.append(cur); chunk_titled.append(titled_next)
                cur, titled_next = [], False
            else:
                cur.append(t)
        if cur:
            chunks.append(cur); chunk_titled.append(titled_next)

        for ch, titled in zip(chunks, chunk_titled):
            # "Milano Mario Rossi" -> "Mario Rossi"
            while len(ch) > 2 and ch[0].group().casefold() in CITIES:
                ch = ch[1:]
            while len(ch) > 2 and ch[-1].group().casefold() in CITIES:
                ch = ch[:-1]
            s, e = base + ch[0].start(), base + ch[-1].end()
            before = text[max(0, s - 40):s]
            if not titled and RX_TITLE_BEFORE.search(before):
                titled = True
            triggered = bool(RX_TRIGGER_BEFORE.search(before))
            words = [t.group().casefold() for t in ch]
            if len(words) > 4:
                continue
            # "Booking.com", "Rossi@..." -> non è un nome di persona
            if re.match(r"[.@][\w]", text[e:e + 2]):
                continue
            has_first = any(w in first_names for w in words)
            if ((titled and len(words) >= 1) or (len(words) >= 2 and (has_first or triggered))):
                # una sola parola in maiuscolo dopo un titolo tipo "Ill.mo GIUDICE" non è un nome
                if len(words) == 1 and ch[0].group().isupper() and len(ch[0].group()) > 1:
                    continue
                results.append((s, e))
    # elenchi: "Mario Rossi, Anna Bianchi e Luca Verdi" -> anche gli elementi successivi
    extra = []
    for s, e in results:
        pos = e
        while True:
            sep = RX_LIST_SEP.match(text, pos)
            if not sep:
                break
            nxt = RX_NAME_SEQ.match(text, sep.end())
            if not nxt:
                break
            toks = [t.group() for t in RX_NAME_TOKEN.finditer(nxt.group())]
            if not (2 <= len(toks) <= 4) or any(t.casefold() in STOPWORDS | TITLE_WORDS for t in toks):
                break
            extra.append((nxt.start(), nxt.end()))
            pos = nxt.end()
    return results + extra


def _trim(val: str, keep_dot: bool = False) -> str:
    """Toglie punteggiatura ai bordi lasciando le parentesi bilanciate."""
    edge = " \t\n,;:-–\"'<>[]" + ("" if keep_dot else ".")
    prev = None
    while prev != val:
        prev = val
        val = val.strip(edge)
        if val.startswith("(") and ")" not in val:
            val = val[1:]
        if val.endswith(")") and "(" not in val:
            val = val[:-1]
    return val


def _person_group(name: str) -> str:
    toks = name.casefold().split()
    return f"{toks[0]}|{toks[-1]}" if len(toks) > 1 else toks[0]


# --------------------------------------------------------------------------- API

def detect(text: str, opts: Options) -> list[Entity]:
    text = clean(text)
    cats = opts.categories
    first_names = FIRST_NAMES | {n.casefold() for n in opts.extra_names}
    found: list[tuple[int, int, str, str]] = []   # (start, end, categoria, gruppo)

    def add(rx, cat, group_idx=0, validator=None, group_fn=None):
        if cat not in cats:
            return
        for m in rx.finditer(text):
            s, e = m.span(group_idx)
            val = text[s:e]
            if validator and not validator(val):
                continue
            found.append((s, e, cat, group_fn(val) if group_fn else ""))

    # ordine = priorità in caso di sovrapposizione
    add(RX_EMAIL, "EMAIL")
    add(RX_URL, "URL", validator=lambda v: True)
    add(RX_IBAN, "IBAN", validator=valid_iban)
    add(RX_CF, "CF")
    add(RX_PIVA_CTX, "PIVA", 1)
    add(RX_PIVA_BARE, "PIVA", 1, validator=valid_piva)
    add(RX_BIRTH, "DATA_NASCITA", 1)
    add(RX_CODE_CTX, "CODICE", 1, validator=lambda v: any(c.isdigit() for c in v))
    add(RX_PHONE, "TELEFONO", validator=lambda v: not RX_DATE_LIKE.fullmatch(v.strip()))
    add(RX_ADDR_IT, "INDIRIZZO")
    add(RX_ADDR_FOREIGN, "INDIRIZZO")
    add(RX_ETICKET, "CODICE")
    add(RX_PNR, "CODICE", validator=lambda v: not RX_FLIGHT.fullmatch(v))
    add(RX_PLATE, "CODICE")

    companies: list[tuple[int, int, str]] = []
    if "SOCIETA" in cats:
        for m in RX_COMPANY.finditer(text):
            raw = re.sub(r"^\d+\.\s*", "", m.group(1))        # "18.Booking.com" -> "Booking.com"
            name_toks = raw.split()
            cut = max((i + 1 for i, t in enumerate(name_toks[:-1]) if t[-1] in ".,;:"), default=0)
            name_toks = name_toks[cut:]
            while name_toks and name_toks[0].casefold().strip(".,") in STOPWORDS:
                name_toks.pop(0)
            if not name_toks:
                continue
            base = " ".join(name_toks)
            s = m.start(1) + m.group(1).find(name_toks[0])
            companies.append((s, m.end(), base))
        # "Customer Relations Booking.com B.V." -> si riduce a "Booking.com B.V." se già noto
        bases = sorted({c[2] for c in companies}, key=len)
        for i, (s, e, base) in enumerate(companies):
            for short in bases:
                if len(short) < len(base) and base.endswith(" " + short):
                    s += len(base) - len(short)
                    base = short
                    break
            companies[i] = (s, e, base)
            found.append((s, e, "SOCIETA", norm_key(base)))

    if "PERSONA" in cats:
        for s, e in _person_candidates(text, first_names):
            found.append((s, e, "PERSONA", _person_group(text[s:e])))

    # risoluzione delle sovrapposizioni (vince il primo in ordine di priorità)
    taken: list[tuple[int, int]] = []
    entities: dict[str, Entity] = {}
    for s, e, cat, grp in found:
        val = _trim(text[s:e], keep_dot=cat in ("CF", "EMAIL", "URL", "INDIRIZZO", "SOCIETA"))
        if len(val) < 2 or any(s < te and ts < e for ts, te in taken):
            continue
        if norm_key(val) in opts.whitelist:
            continue
        taken.append((s, e))
        k = norm_key(val)
        if k not in entities:
            entities[k] = Entity(val, cat, grp or k)

    # propagazione: il cognome da solo -> persona con più occorrenze che lo porta
    def occurrences(t: str) -> int:
        return len(re.findall(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I))

    persons = sorted((e for e in entities.values() if e.category == "PERSONA"),
                     key=lambda e: occurrences(e.text), reverse=True)
    surname_owner: dict[str, str] = {}
    for ent in (p for p in persons if len(p.text.split()) > 1):
        for tok in ent.text.split():
            c = tok.casefold()
            if len(c) >= 3 and c not in first_names and c not in PARTICLES and c not in CITIES:
                surname_owner.setdefault(c, ent.group)
    for sur, grp in surname_owner.items():
        if sur in entities and entities[sur].category == "PERSONA":
            entities[sur].group = grp          # "la signora Bianchi" -> stessa persona di "Giulia Bianchi"
        if sur in entities or sur in opts.whitelist:
            continue
        m = re.search(rf"(?<!\w){re.escape(sur)}(?!\w)", text, re.I)
        if m:
            entities[sur] = Entity(m.group(), "PERSONA", grp)
        # "M. Rossi" -> la persona con quel cognome e nome che inizia per M
        for m in re.finditer(rf"(?<!\w)([{UP}])\.\s*({re.escape(sur)})(?!\w)", text, re.I):
            if not m.group(1).isupper():
                continue
            owner = next((p.group for p in persons
                          if p.text.split()[0][0].upper() == m.group(1)
                          and sur in p.text.casefold().split()), grp)
            k = norm_key(m.group())
            if k not in entities:
                entities[k] = Entity(m.group(), "PERSONA", owner)
    for _, _, base in companies:
        k = norm_key(base)
        if k not in entities and k not in opts.whitelist and len(base) >= 3:
            entities[k] = Entity(base, "SOCIETA", k)

    # termini da anonimizzare sempre (impostazioni)
    for term, cat in opts.always_terms:
        k = norm_key(term)
        if k and k not in entities:
            entities[k] = Entity(term, cat if cat in CATEGORIES else "MANUALE", source="manuale")

    ents = list(entities.values())
    recount(ents, text)
    # elimina varianti mai presenti da sole (es. cognome sempre dentro il nome completo)
    ents = [e for e in ents if e.count > 0 or e.source == "manuale"]
    ents.sort(key=lambda e: e.first_pos)
    return ents
