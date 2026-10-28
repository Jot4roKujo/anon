"""Anonimizzatore Documenti — interfaccia grafica (tkinter).

Flusso: Apri documento (.docx/.pdf) -> Analizza -> rivedi i dati trovati
(attiva/disattiva, modifica la sostituzione, aggiungi ciò che manca selezionandolo
nell'anteprima) -> Anonimizza e salva. Dopo il salvataggio il file prodotto viene
riletto per verificare che nessun dato attivo sia rimasto.
"""
from __future__ import annotations

import sys

if __name__ == "__main__" and sys.argv[1:2] == ["--self-test"]:
    # prima di ogni altro import, così anche un modulo mancante nel pacchetto viene segnalato
    from anon.selftest import main as _self_test
    sys.exit(_self_test(sys.argv[2:]))

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from anon import pipeline
from anon.detector import _person_group
from anon.model import CATEGORIES, MODES, Entity, Matcher, Options, assign_replacements, norm_key

try:  # trascinamento file (opzionale: pip install tkinterdnd2)
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover
    TkinterDnD = None

APP_NAME = "Anonimizzatore Documenti"
IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"          # ⌘ su Mac, Ctrl altrove
VERSION = "1.0"

C = dict(bg="#1e1f22", panel="#2b2d31", panel2="#313338", field="#232428", fg="#e3e5e8",
         muted="#949ba4", accent="#4f8cff", accent2="#3b6fd6", border="#3f4147",
         sel="#3a4a6b", warn="#f0b232", danger="#f23f43", ok="#23a55a")


def settings_path() -> str:
    if IS_MAC:
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, "AnonimizzatoreDocumenti")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def open_with_system(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        messagebox.showerror(APP_NAME, f"Impossibile aprire il file:\n{exc}")


def _blend(hex_color: str, alpha: float, bg: str = C["field"]) -> str:
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02x}" for x, y in zip(a, b))


class App:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.configure(bg=C["bg"])
        self.root.minsize(1050, 640)

        self.src: pipeline.Source | None = None
        self.entities: list[Entity] = []
        self.iid2ent: dict[str, Entity] = {}
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False

        self.settings = self._load_settings()
        self.root.geometry(self.settings.get("geometry", "1280x800"))

        self.var_cat = {k: tk.BooleanVar(value=k in self.settings["categories"]) for k in CATEGORIES
                        if k != "MANUALE"}
        self.var_mode = tk.StringVar(value=self.settings["mode"])
        self.var_pdf = tk.StringVar(value=self.settings["pdf_style"])
        self.var_meta = tk.BooleanVar(value=self.settings["strip_metadata"])
        self.var_map = tk.BooleanVar(value=self.settings["export_map"])
        self.var_view = tk.StringVar(value="orig")
        self.var_file = tk.StringVar(value="Nessun documento — apri un file .docx o .pdf (o trascinalo qui)")
        self.var_stats = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="Pronto.")

        self._style()
        self._build()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_jobs)

    # ------------------------------------------------------------------ impostazioni
    def _load_settings(self) -> dict:
        d = Options()
        defaults = dict(categories=sorted(d.categories), mode=d.mode, pdf_style=d.pdf_style,
                        strip_metadata=d.strip_metadata, export_map=d.export_map, whitelist=[],
                        extra_names=[], always_terms=[], last_dir=os.path.expanduser("~"))
        try:
            with open(settings_path(), encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
        return defaults

    def _save_settings(self) -> None:
        self.settings.update(
            categories=[k for k, v in self.var_cat.items() if v.get()], mode=self.var_mode.get(),
            pdf_style=self.var_pdf.get(), strip_metadata=self.var_meta.get(),
            export_map=self.var_map.get(), geometry=self.root.geometry())
        try:
            with open(settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def options(self) -> Options:
        s = self.settings
        return Options(
            categories={k for k, v in self.var_cat.items() if v.get()} | {"MANUALE"},
            mode=self.var_mode.get(), pdf_style=self.var_pdf.get(),
            strip_metadata=self.var_meta.get(), export_map=self.var_map.get(),
            whitelist={norm_key(w) for w in s["whitelist"]}, extra_names=set(s["extra_names"]),
            always_terms=[(t, "MANUALE") for t in s["always_terms"]])

    # ------------------------------------------------------------------ stile
    def _style(self) -> None:
        fams = set(tkfont.families())
        family = next((f for f in ("Segoe UI", ".AppleSystemUIFont", "SF Pro Text", "Helvetica Neue",
                                   "Inter", "DejaVu Sans")
                       if f in fams), "TkDefaultFont")
        self.font = (family, 10)
        self.font_b = (family, 10, "bold")
        self.font_title = (family, 15, "bold")
        self.font_small = (family, 9)
        mono = next((f for f in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono") if f in fams),
                    "TkFixedFont")
        self.font_text = (family, 10)
        self.font_mono = (mono, 9)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass

        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=C["bg"], foreground=C["fg"], fieldbackground=C["field"],
                     bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"],
                     troughcolor=C["panel"], focuscolor=C["accent"], font=self.font,
                     selectbackground=C["sel"], selectforeground=C["fg"], insertcolor=C["fg"])
        st.configure("TFrame", background=C["bg"])
        st.configure("Panel.TFrame", background=C["panel"])
        st.configure("TLabel", background=C["bg"], foreground=C["fg"])
        st.configure("Panel.TLabel", background=C["panel"])
        st.configure("Muted.TLabel", foreground=C["muted"])
        st.configure("PanelMuted.TLabel", background=C["panel"], foreground=C["muted"], font=self.font_small)
        st.configure("Section.TLabel", background=C["panel"], foreground=C["muted"], font=self.font_b)
        st.configure("Title.TLabel", font=self.font_title)
        st.configure("Status.TLabel", background=C["panel"], foreground=C["muted"], padding=(10, 4))
        st.configure("TCheckbutton", background=C["panel"], foreground=C["fg"], padding=(2, 3),
                     indicatorbackground=C["field"], indicatorforeground=C["fg"])
        st.map("TCheckbutton", background=[("active", C["panel"])],
               indicatorbackground=[("selected", C["accent"]), ("active", C["panel2"])])
        st.configure("TRadiobutton", background=C["panel"], foreground=C["fg"], padding=(2, 3),
                     indicatorbackground=C["field"], indicatorforeground=C["fg"])
        st.map("TRadiobutton", background=[("active", C["panel"])],
               indicatorbackground=[("selected", C["accent"]), ("active", C["panel2"])])
        st.configure("Seg.TRadiobutton", background=C["bg"])
        st.map("Seg.TRadiobutton", background=[("active", C["bg"])])
        st.configure("TButton", background=C["panel2"], foreground=C["fg"], padding=(12, 6),
                     borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("disabled", C["panel"]), ("pressed", C["border"]),
                                      ("active", C["border"])],
               foreground=[("disabled", C["muted"])])
        st.configure("Accent.TButton", background=C["accent"], foreground="#ffffff", font=self.font_b)
        st.map("Accent.TButton", background=[("disabled", C["panel2"]), ("pressed", C["accent2"]),
                                             ("active", C["accent2"])])
        st.configure("Small.TButton", padding=(8, 4))
        st.configure("Treeview", background=C["field"], fieldbackground=C["field"], foreground=C["fg"],
                     rowheight=26, borderwidth=0)
        st.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", C["fg"])])
        st.configure("Treeview.Heading", background=C["panel2"], foreground=C["muted"],
                     font=self.font_b, borderwidth=0, padding=(6, 5))
        st.map("Treeview.Heading", background=[("active", C["border"])])
        st.configure("TPanedwindow", background=C["bg"])
        st.configure("Sash", sashthickness=6, gripcount=0, background=C["bg"])
        st.configure("Vertical.TScrollbar", background=C["panel2"], arrowcolor=C["muted"],
                     troughcolor=C["field"], borderwidth=0)
        st.configure("TEntry", fieldbackground=C["field"], foreground=C["fg"], padding=5)
        st.configure("TCombobox", fieldbackground=C["field"], background=C["panel2"],
                     foreground=C["fg"], arrowcolor=C["fg"], padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])])
        self.root.option_add("*TCombobox*Listbox.background", C["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["sel"])
        self.root.option_add("*Menu.background", C["panel2"])
        self.root.option_add("*Menu.foreground", C["fg"])
        self.root.option_add("*Menu.activeBackground", C["sel"])
        self.root.option_add("*Menu.activeForeground", C["fg"])
        self.root.option_add("*Menu.relief", "flat")

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(2, weight=1)

        head = ttk.Frame(r, padding=(16, 12, 16, 6))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text="Anonimizzatore", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(head, text="Word e PDF · tutto in locale, nessun dato esce dal PC",
                  style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=12)

        bar = ttk.Frame(r, padding=(16, 4, 16, 10))
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        ttk.Button(bar, text="Apri documento…", command=self.open_file).grid(row=0, column=0)
        self.lbl_file = ttk.Label(bar, textvariable=self.var_file, style="Muted.TLabel")
        self.lbl_file.grid(row=0, column=1, sticky="w", padx=12)
        self.btn_analyze = ttk.Button(bar, text="Analizza  (⌘R)" if IS_MAC else "Analizza  (F5)", command=self.analyze, state="disabled")
        self.btn_analyze.grid(row=0, column=2, padx=(0, 8))
        self.btn_save = ttk.Button(bar, text="Anonimizza e salva…", style="Accent.TButton",
                                   command=self.save, state="disabled")
        self.btn_save.grid(row=0, column=3)

        main = ttk.PanedWindow(r, orient="horizontal")
        main.grid(row=2, column=0, sticky="nsew", padx=16)
        main.add(self._build_sidebar(main), weight=0)

        center = ttk.PanedWindow(main, orient="vertical")
        main.add(center, weight=1)
        center.add(self._build_table(center), weight=3)
        center.add(self._build_preview(center), weight=2)

        status = ttk.Label(r, textvariable=self.var_status, style="Status.TLabel", anchor="w")
        status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        if TkinterDnD:
            r.drop_target_register(DND_FILES)
            r.dnd_bind("<<Drop>>", self._on_drop)

    def _build_sidebar(self, parent) -> ttk.Frame:
        side = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        side.columnconfigure(0, weight=1)
        row = 0

        def section(text):
            nonlocal row
            ttk.Label(side, text=text.upper(), style="Section.TLabel").grid(
                row=row, column=0, sticky="w", pady=(10 if row else 0, 4))
            row += 1

        section("Dati da cercare")
        for key, var in self.var_cat.items():
            ttk.Checkbutton(side, text=CATEGORIES[key].label, variable=var,
                            command=self._on_categories).grid(row=row, column=0, sticky="w")
            row += 1

        section("Sostituisci con")
        for key, label in (("tag", "Etichette  [PERSONA_1]"), ("iniziali", "Iniziali  J.S."),
                           ("omissis", "[omissis]")):
            ttk.Radiobutton(side, text=label, value=key, variable=self.var_mode,
                            command=self._on_mode).grid(row=row, column=0, sticky="w")
            row += 1

        section("PDF")
        ttk.Radiobutton(side, text="Riquadro con etichetta", value="label",
                        variable=self.var_pdf).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Radiobutton(side, text="Riquadro nero", value="black",
                        variable=self.var_pdf).grid(row=row, column=0, sticky="w")
        row += 1

        section("Opzioni")
        ttk.Checkbutton(side, text="Rimuovi metadati (autore…)", variable=self.var_meta).grid(
            row=row, column=0, sticky="w")
        row += 1
        ttk.Checkbutton(side, text="Esporta tabella corrispondenze", variable=self.var_map).grid(
            row=row, column=0, sticky="w")
        row += 1
        ttk.Label(side, text="CSV con originale → sostituzione:\nconservalo separato dal documento.",
                  style="PanelMuted.TLabel").grid(row=row, column=0, sticky="w", padx=(24, 0))
        row += 1
        ttk.Button(side, text="Eccezioni e nomi…", command=self.edit_lists).grid(
            row=row, column=0, sticky="ew", pady=(14, 0))
        return side

    def _build_table(self, parent) -> ttk.Frame:
        fr = ttk.Frame(parent, padding=(10, 0, 0, 6))
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        top = ttk.Frame(fr)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="Dati trovati", font=self.font_b).grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.var_stats, style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        cols = ("on", "testo", "cat", "sost", "occ")
        tv = ttk.Treeview(fr, columns=cols, show="headings", selectmode="extended")
        for c, text, w, anchor, stretch in (("on", "✓", 34, "center", False),
                                            ("testo", "Testo trovato", 300, "w", True),
                                            ("cat", "Categoria", 150, "w", False),
                                            ("sost", "Sostituito con", 170, "w", False),
                                            ("occ", "Volte", 60, "e", False)):
            tv.heading(c, text=text, anchor=anchor)
            tv.column(c, width=w, minwidth=30, anchor=anchor, stretch=stretch)
        for key, cat in CATEGORIES.items():
            tv.tag_configure(key, foreground=cat.color)
        tv.tag_configure("off", foreground=C["muted"])
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        self.tree = tv

        btns = ttk.Frame(fr)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for text, cmd in (("Attiva / disattiva  (Spazio)", self.toggle_selected),
                          ("Modifica sostituzione…", self.edit_replacement),
                          ("Aggiungi termine…", self.add_term),
                          ("Rimuovi  (⌫)" if IS_MAC else "Rimuovi  (Canc)", self.remove_selected)):
            ttk.Button(btns, text=text, style="Small.TButton", command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(btns, text="Doppio clic: ✓ attiva/disattiva, testo modifica",
                  style="Muted.TLabel").pack(side="right")

        tv.bind("<Double-1>", self._on_tree_double)
        tv.bind("<<TreeviewSelect>>", lambda e: self._highlight_selected())
        tv.bind("<space>", lambda e: (self.toggle_selected(), "break")[1])
        tv.bind("<Delete>", lambda e: self.remove_selected())
        tv.bind("<BackSpace>", lambda e: self.remove_selected())
        self._bind_context(tv, self._tree_menu)
        return fr

    def _build_preview(self, parent) -> ttk.Frame:
        fr = ttk.Frame(parent, padding=(10, 6, 0, 0))
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)
        top = ttk.Frame(fr)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(top, text="Anteprima", font=self.font_b).pack(side="left")
        for val, text in (("orig", "Originale evidenziato"), ("anon", "Risultato")):
            ttk.Radiobutton(top, text=text, value=val, variable=self.var_view, style="Seg.TRadiobutton",
                            command=self.render_preview).pack(side="left", padx=(14, 0))
        ttk.Label(top, text="Seleziona del testo e clic destro per anonimizzarlo",
                  style="Muted.TLabel").pack(side="right")

        txt = tk.Text(fr, wrap="word", bg=C["field"], fg=C["fg"], insertbackground=C["fg"],
                      relief="flat", padx=14, pady=10, font=self.font_text, spacing1=1, spacing3=3,
                      selectbackground=C["accent2"], selectforeground="#ffffff", highlightthickness=0,
                      undo=False)
        sb = ttk.Scrollbar(fr, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        for key, cat in CATEGORIES.items():
            txt.tag_configure(key, background=_blend(cat.color, 0.28), foreground="#ffffff")
        txt.tag_configure("current", background=C["accent"], foreground="#ffffff")
        txt.tag_raise("current")
        txt.tag_raise("sel")
        # sola lettura ma selezionabile
        copy_mask = 8 if IS_MAC else 4                       # ⌘ su Mac, Ctrl altrove
        txt.bind("<Key>", lambda e: None if (e.state & copy_mask and e.keysym.lower() in ("c", "a"))
                 else "break")
        self._bind_context(txt, self._text_menu)
        self.text = txt
        return fr

    @staticmethod
    def _bind_context(widget, handler) -> None:
        if IS_MAC:
            widget.bind("<Button-2>", handler)
            widget.bind("<Control-Button-1>", handler)
        widget.bind("<Button-3>", handler)

    def _bind_keys(self) -> None:
        self.root.bind(f"<{MOD}-o>", lambda e: self.open_file())
        self.root.bind(f"<{MOD}-s>", lambda e: self.save())
        self.root.bind("<F5>", lambda e: self.analyze())
        if IS_MAC:
            self.root.bind("<Command-r>", lambda e: self.analyze())
            # file aperto dal Finder ("Apri con"), o trascinato sull'icona nel Dock
            self.root.createcommand("::tk::mac::OpenDocument",
                                    lambda *paths: paths and self.root.after(50, self.open_file, paths[0]))
            self.root.createcommand("::tk::mac::Quit", self._on_close)

    # ------------------------------------------------------------------ lavori in background
    def _run(self, label: str, fn, done) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_buttons()
        self.var_status.set(label)
        self.root.config(cursor="watch")

        def worker():
            try:
                self.jobs.put((done, fn(), None))
            except Exception as exc:  # noqa: BLE001
                self.jobs.put((done, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self) -> None:
        try:
            while True:
                done, result, exc = self.jobs.get_nowait()
                self.busy = False
                self.root.config(cursor="")
                self._set_buttons()
                if exc:
                    self.var_status.set("Errore.")
                    messagebox.showerror(APP_NAME, str(exc), parent=self.root)
                else:
                    done(result)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_jobs)

    def _set_buttons(self) -> None:
        has_src = self.src is not None and not self.busy
        self.btn_analyze.configure(state="normal" if has_src else "disabled")
        self.btn_save.configure(state="normal" if has_src and self.entities else "disabled")

    # ------------------------------------------------------------------ azioni principali
    def _on_drop(self, event) -> None:
        files = self.root.tk.splitlist(event.data)
        if files:
            self.open_file(files[0])

    def open_file(self, path: str | None = None) -> None:
        if self.busy:
            return
        if not path:
            path = filedialog.askopenfilename(
                parent=self.root, title="Scegli il documento da anonimizzare",
                initialdir=self.settings.get("last_dir"),
                filetypes=[("Documenti", "*.docx *.pdf"), ("Word", "*.docx"), ("PDF", "*.pdf")])
        if not path:
            return
        self.settings["last_dir"] = os.path.dirname(path)
        self._run("Lettura del documento…", lambda: pipeline.load(path), self._loaded)

    def _loaded(self, src: pipeline.Source) -> None:
        self.src = src
        self.entities = []
        kind = "Word" if src.kind == "docx" else "PDF"
        self.var_file.set(f"{os.path.basename(src.path)}   ·   {kind}, {len(src.text.split()):,} parole"
                          .replace(",", "."))
        for w in src.warnings:
            messagebox.showwarning(APP_NAME, w, parent=self.root)
        self.analyze()

    def analyze(self, keep_user_changes: bool = False) -> None:
        if not self.src or self.busy:
            return
        src, opts = self.src, self.options()
        previous = list(self.entities) if keep_user_changes else []
        self._run("Ricerca dei dati personali…", lambda: pipeline.analyze(src, opts),
                  lambda ents: self._analyzed(ents, previous))

    def _analyzed(self, ents: list[Entity], previous: list[Entity]) -> None:
        if previous:   # riporta le scelte manuali fatte prima della nuova analisi
            prev = {e.key: e for e in previous}
            for e in ents:
                p = prev.get(e.key)
                if p:
                    e.enabled = p.enabled
                    if p.custom_replacement:
                        e.replacement, e.custom_replacement = p.replacement, True
            keys = {e.key for e in ents}
            ents += [p for p in previous if p.source == "manuale" and p.key not in keys]
            pipeline.refresh(self.src, ents, self.var_mode.get())
        self.entities = ents
        self.refresh_all()
        n = len(ents)
        self.var_status.set(f"Analisi completata: {n} dati trovati. Controlla l'elenco, poi "
                            "«Anonimizza e salva».")

    def save(self) -> None:
        if not self.src or not self.entities or self.busy:
            return
        if not any(e.enabled for e in self.entities):
            messagebox.showinfo(APP_NAME, "Non ci sono dati attivi da anonimizzare.", parent=self.root)
            return
        ext = os.path.splitext(self.src.path)[1]
        out = filedialog.asksaveasfilename(
            parent=self.root, title="Salva documento anonimizzato", defaultextension=ext,
            initialdir=os.path.dirname(self.src.path),
            initialfile=os.path.basename(pipeline.default_output(self.src.path)),
            filetypes=[("Word" if ext == ".docx" else "PDF", f"*{ext}")])
        if not out:
            return
        src, ents, opts = self.src, self.entities, self.options()
        self._save_settings()
        self._run("Anonimizzazione e verifica in corso…",
                  lambda: pipeline.export(src, ents, out, opts), self._saved)

    def _saved(self, rep: pipeline.Report) -> None:
        name = os.path.basename(rep.output)
        self.var_status.set(f"Salvato {name}: {rep.replaced} sostituzioni.")
        msg = f"Salvato:\n{rep.output}\n\nSostituzioni effettuate: {rep.replaced}"
        if rep.map_path:
            msg += f"\nTabella corrispondenze: {os.path.basename(rep.map_path)}"
        if rep.residual:
            left = "\n".join(f"  • {e.text}" for e in rep.residual[:15])
            msg += ("\n\nATTENZIONE — nel file prodotto sono ancora presenti:\n" + left +
                    "\n\n(succede di solito con parole spezzate a fine riga nei PDF: "
                    "controlla quei punti a mano)")
            icon = "warning"
        else:
            msg += "\n\nVerifica: nessun dato attivo è rimasto nel file."
            icon = "info"
        if messagebox.askyesno(APP_NAME, msg + "\n\nAprire il documento?", icon=icon, parent=self.root):
            open_with_system(rep.output)

    # ------------------------------------------------------------------ modifiche manuali
    def selected(self) -> list[Entity]:
        return [self.iid2ent[i] for i in self.tree.selection() if i in self.iid2ent]

    def _changed(self, select: list[Entity] | None = None) -> None:
        if self.src:
            pipeline.refresh(self.src, self.entities, self.var_mode.get())
        self.refresh_all(select)

    def toggle_selected(self) -> None:
        sel = self.selected()
        if not sel:
            return
        state = not all(e.enabled for e in sel)
        for e in sel:
            e.enabled = state
        self._changed(sel)

    def remove_selected(self) -> None:
        sel = self.selected()
        if not sel:
            return
        ids = {id(e) for e in sel}
        self.entities = [e for e in self.entities if id(e) not in ids]
        self._changed()

    def edit_replacement(self, ent: Entity | None = None) -> None:
        ent = ent or (self.selected() or [None])[0]
        if not ent:
            return
        group = [e for e in self.entities if e.category == ent.category and e.group == ent.group]
        val = self._ask(f"Sostituzione per «{ent.text}»",
                        "Testo da mettere al posto del dato" +
                        (f" (vale per tutte le {len(group)} varianti dello stesso soggetto)"
                         if len(group) > 1 else "") + ":",
                        ent.replacement)
        if val is None:
            return
        for e in group:
            if val.strip():
                e.replacement, e.custom_replacement = val, True
            else:
                e.custom_replacement = False
        self._changed(group)

    def set_category(self, cat: str) -> None:
        sel = self.selected()
        for e in sel:
            e.category = cat
            e.group = _person_group(e.text) if cat == "PERSONA" else e.key
            e.custom_replacement = False
        self._changed(sel)

    def add_term(self, text: str = "", cat: str = "MANUALE") -> None:
        if not self.src:
            return
        if not text:
            res = self._ask_term()
            if not res:
                return
            text, cat = res
        ent = Entity(text, cat, source="manuale")
        if cat == "PERSONA":
            ent.group = _person_group(ent.text)
        existing = next((e for e in self.entities if e.key == ent.key), None)
        if existing:
            existing.enabled = True
            self._changed([existing])
            return
        self.entities.append(ent)
        self._changed([ent])
        if ent.count == 0:
            self.var_status.set(f"«{text}» non compare nel testo così com'è scritto (controlla spazi e "
                                "punteggiatura).")

    def never_anonymize(self) -> None:
        sel = self.selected()
        if not sel:
            return
        if not messagebox.askyesno(APP_NAME, "Non anonimizzare mai, anche nei prossimi documenti:\n\n" +
                                   "\n".join(f"  • {e.text}" for e in sel), parent=self.root):
            return
        wl = self.settings["whitelist"]
        wl += [e.text for e in sel if e.text not in wl]
        self._save_settings()
        self.remove_selected()

    def always_anonymize(self) -> None:
        sel = self.selected()
        terms = self.settings["always_terms"]
        terms += [e.text for e in sel if e.text not in terms]
        self._save_settings()
        self.var_status.set(f"{len(sel)} termini verranno cercati sempre, anche nei prossimi documenti.")

    def edit_lists(self) -> None:
        dlg = tk.Toplevel(self.root, bg=C["bg"])
        dlg.title("Eccezioni e nomi")
        dlg.transient(self.root)
        dlg.geometry("760x460")
        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill="both", expand=True)
        boxes = {}
        specs = (("whitelist", "Non anonimizzare mai", "Es. nomi di giudici,\nenti pubblici, il tuo studio"),
                 ("extra_names", "Nomi propri in più", "Nomi rari che il programma\nnon riconosce da solo"),
                 ("always_terms", "Anonimizza sempre", "Termini cercati in\nogni documento"))
        for col, (key, title, hint) in enumerate(specs):
            frame.columnconfigure(col, weight=1)
            ttk.Label(frame, text=title, font=self.font_b).grid(row=0, column=col, sticky="w", padx=6)
            ttk.Label(frame, text=hint + "\n(uno per riga)", style="Muted.TLabel").grid(
                row=1, column=col, sticky="w", padx=6, pady=(0, 6))
            t = tk.Text(frame, height=16, width=24, bg=C["field"], fg=C["fg"], insertbackground=C["fg"],
                        relief="flat", padx=8, pady=6, font=self.font, highlightthickness=1,
                        highlightbackground=C["border"], highlightcolor=C["accent"])
            t.grid(row=2, column=col, sticky="nsew", padx=6)
            t.insert("1.0", "\n".join(self.settings[key]))
            boxes[key] = t
        frame.rowconfigure(2, weight=1)

        def ok():
            for key, t in boxes.items():
                self.settings[key] = [ln.strip() for ln in t.get("1.0", "end").splitlines() if ln.strip()]
            self._save_settings()
            dlg.destroy()
            if self.src:
                self.analyze(keep_user_changes=True)

        b = ttk.Frame(frame)
        b.grid(row=3, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(b, text="Annulla", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(b, text="Salva e rianalizza", style="Accent.TButton", command=ok).pack(side="right")
        dlg.grab_set()

    # ------------------------------------------------------------------ dialoghi
    def _ask(self, title: str, prompt: str, initial: str = "") -> str | None:
        dlg = tk.Toplevel(self.root, bg=C["bg"])
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        fr = ttk.Frame(dlg, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=prompt, wraplength=420).pack(anchor="w")
        var = tk.StringVar(value=initial)
        ent = ttk.Entry(fr, textvariable=var, width=50)
        ent.pack(fill="x", pady=10)
        ent.select_range(0, "end")
        ent.focus_set()
        result: list[str | None] = [None]

        def ok(_=None):
            result[0] = var.get()
            dlg.destroy()

        b = ttk.Frame(fr)
        b.pack(anchor="e")
        ttk.Button(b, text="Annulla", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(b, text="OK", style="Accent.TButton", command=ok).pack(side="right")
        dlg.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.grab_set()
        self.root.wait_window(dlg)
        return result[0]

    def _ask_term(self) -> tuple[str, str] | None:
        dlg = tk.Toplevel(self.root, bg=C["bg"])
        dlg.title("Aggiungi termine")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        fr = ttk.Frame(dlg, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="Testo da anonimizzare (verrà sostituito ovunque compaia):").pack(anchor="w")
        var = tk.StringVar()
        e = ttk.Entry(fr, textvariable=var, width=50)
        e.pack(fill="x", pady=(6, 10))
        e.focus_set()
        ttk.Label(fr, text="Categoria:").pack(anchor="w")
        labels = {c.label: k for k, c in CATEGORIES.items()}
        cvar = tk.StringVar(value=CATEGORIES["MANUALE"].label)
        ttk.Combobox(fr, textvariable=cvar, values=list(labels), state="readonly").pack(fill="x", pady=(6, 12))
        result: list = [None]

        def ok(_=None):
            if var.get().strip():
                result[0] = (var.get().strip(), labels[cvar.get()])
            dlg.destroy()

        b = ttk.Frame(fr)
        b.pack(anchor="e")
        ttk.Button(b, text="Annulla", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(b, text="Aggiungi", style="Accent.TButton", command=ok).pack(side="right")
        dlg.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda ev: dlg.destroy())
        dlg.grab_set()
        self.root.wait_window(dlg)
        return result[0]

    # ------------------------------------------------------------------ menu contestuali
    def _tree_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
        if not self.selected():
            return
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Attiva / disattiva", command=self.toggle_selected)
        m.add_command(label="Modifica sostituzione…", command=self.edit_replacement)
        cats = tk.Menu(m, tearoff=0)
        for k, c in CATEGORIES.items():
            cats.add_command(label=c.label, command=lambda k=k: self.set_category(k))
        m.add_cascade(label="Cambia categoria", menu=cats)
        m.add_separator()
        m.add_command(label="Non anonimizzare mai (eccezione permanente)", command=self.never_anonymize)
        m.add_command(label="Anonimizza sempre (anche nei prossimi documenti)", command=self.always_anonymize)
        m.add_separator()
        m.add_command(label="Rimuovi dall'elenco", command=self.remove_selected)
        m.tk_popup(event.x_root, event.y_root)

    def _text_menu(self, event) -> None:
        try:
            sel = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            sel = ""
        sel = " ".join(sel.split())
        if not sel or self.var_view.get() != "orig":
            if self.var_view.get() != "orig":
                self.var_status.set("Per aggiungere un termine usa la vista «Originale evidenziato».")
            return
        m = tk.Menu(self.root, tearoff=0)
        short = sel if len(sel) <= 40 else sel[:37] + "…"
        m.add_command(label=f"Anonimizza «{short}» come:", state="disabled")
        for k, c in CATEGORIES.items():
            m.add_command(label=f"    {c.label}", command=lambda k=k: self.add_term(sel, k))
        m.tk_popup(event.x_root, event.y_root)

    def _on_tree_double(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        if self.tree.identify_column(event.x) == "#1":
            self.toggle_selected()
        else:
            self.edit_replacement(self.iid2ent[iid])

    # ------------------------------------------------------------------ opzioni cambiate
    def _on_mode(self) -> None:
        # le sostituzioni scritte a mano restano; le altre si ricalcolano
        assign_replacements(self.entities, self.var_mode.get())
        self.refresh_all(self.selected())
        self._save_settings()

    def _on_categories(self) -> None:
        self._save_settings()
        if self.src:
            self.analyze(keep_user_changes=True)

    # ------------------------------------------------------------------ rendering
    def refresh_all(self, select: list[Entity] | None = None) -> None:
        self.render_table(select)
        self.render_preview()
        on = [e for e in self.entities if e.enabled]
        self.var_stats.set(f"{len(self.entities)} trovati · {len(on)} attivi · "
                           f"{sum(e.count for e in on)} sostituzioni")
        self._set_buttons()

    def render_table(self, select: list[Entity] | None = None) -> None:
        tv = self.tree
        yview = tv.yview()
        tv.delete(*tv.get_children())
        self.iid2ent.clear()
        ids_sel = {id(e) for e in (select or [])}
        to_select = []
        for e in self.entities:      # ordine di rilevamento (non cambia quando si disattiva)
            iid = tv.insert("", "end", values=("✓" if e.enabled else "", e.text,
                                               CATEGORIES[e.category].label,
                                               e.replacement if e.enabled else "— lasciato com'è —",
                                               e.count),
                            tags=(e.category if e.enabled else "off",))
            self.iid2ent[iid] = e
            if id(e) in ids_sel:
                to_select.append(iid)
        if to_select:
            tv.selection_set(to_select)
        tv.yview_moveto(yview[0])

    def render_preview(self) -> None:
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not self.src:
            return
        text = self.src.text
        matches = list(Matcher(self.entities).finditer(text))
        if self.var_view.get() == "orig":
            t.insert("1.0", text)
            for s, e, ent in matches:
                t.tag_add(ent.category, f"1.0+{s}c", f"1.0+{e}c")
        else:
            last = 0
            for s, e, ent in matches:
                t.insert("end", text[last:s])
                t.insert("end", ent.replacement, (ent.category,))
                last = e
            t.insert("end", text[last:])
        self._highlight_selected(scroll=False)

    def _highlight_selected(self, scroll: bool = True) -> None:
        t = self.text
        t.tag_remove("current", "1.0", "end")
        sel = self.selected()
        if not sel or not self.src or self.var_view.get() != "orig":
            return
        probes = [Entity(x.text, x.category) for x in sel]   # anche se disattivate
        first = None
        for s, e, _ in Matcher(probes).finditer(self.src.text):
            t.tag_add("current", f"1.0+{s}c", f"1.0+{e}c")
            first = first if first is not None else s
        if scroll and first is not None:
            t.see(f"1.0+{first}c")

    # ------------------------------------------------------------------ chiusura
    def _on_close(self) -> None:
        self._save_settings()
        self.root.destroy()

    def run(self) -> None:
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.root.after(200, lambda: self.open_file(sys.argv[1]))
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
