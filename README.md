# Anonimizzatore Documenti

Tool desktop (Python + tkinter) per anonimizzare atti e documenti **Word (.docx)** e **PDF**.
Funziona interamente in locale: nessun dato viene inviato a servizi esterni.

## Avvio rapido

```bat
pip install -r requirements.txt
python app.py
```

## Compilare l'applicazione

PyInstaller compila solo per il sistema su cui gira: l'`.exe` si crea su Windows, l'`.app`
su un Mac. Le opzioni di build sono tutte in `Anonimizzatore.spec`.

| Sistema | Come | Risultato |
|---|---|---|
| Windows | doppio clic su `build.bat` | `dist\Anonimizzatore.exe` |
| macOS | `./build_mac.sh` dal Terminale | `dist/Anonimizzatore.app` + `dist/Anonimizzatore-macOS-<arch>.dmg` |
| Senza Mac | GitHub Actions (vedi sotto) | `.dmg` Apple Silicon, `.dmg` Intel, `.exe` |

### macOS

1. Serve un Python con Tk: installalo da [python.org](https://www.python.org/downloads/macos/)
   (3.12 o 3.13). Il `python3` di Apple e quello di Homebrew senza `python-tk` non vanno bene:
   lo script lo controlla e lo dice.
2. Nella cartella del progetto: `chmod +x build_mac.sh && ./build_mac.sh`
   (con un Python specifico: `PYTHON=/usr/local/bin/python3.12 ./build_mac.sh`).
3. Apri il `.dmg` e trascina l'app in Applicazioni.

L'app è compilata per l'architettura del Mac su cui la crei (`arm64` = Apple Silicon,
`x86_64` = Intel). La versione Intel gira anche su Apple Silicon tramite Rosetta, non il contrario.

Su macOS l'app compare in **Apri con** per PDF e Word, accetta i file trascinati sull'icona
nel Dock e usa ⌘O / ⌘S / ⌘R. Le impostazioni stanno in
`~/Library/Application Support/AnonimizzatoreDocumenti/`.

**Primo avvio di un'app scaricata.** L'app ha una firma "ad-hoc", non un certificato Apple.
Se l'hai compilata sul tuo Mac si apre normalmente. Se invece l'hai scaricata (da GitHub,
email, chiavetta) macOS la blocca: apri **Impostazioni di Sistema → Privacy e sicurezza**
e premi **Apri comunque**, oppure da Terminale:

```bash
xattr -dr com.apple.quarantine /Applications/Anonimizzatore.app
```

Per distribuirla ad altri senza questo passaggio serve un account Apple Developer
(Developer ID + notarizzazione).

### Build automatica con GitHub Actions

Il file `.github/workflows/build.yml` compila tutto sui server di GitHub, senza un Mac:
carica il progetto in un repository (anche privato), vai su **Actions → Build → Run workflow**
e, a fine esecuzione, scarica i file da **Artifacts**. Parte da sola anche quando pubblichi
un tag `v…` (es. `v1.0`).

### Autotest dell'eseguibile

```bash
Anonimizzatore --self-test [report.txt]          # Windows: Anonimizzatore.exe --self-test report.txt
dist/Anonimizzatore.app/Contents/MacOS/Anonimizzatore --self-test
```

Controlla senza aprire finestre che nel pacchetto ci sia tutto (Tcl/Tk, Word, PDF) e
anonimizza un documento di prova. La build automatica lo esegue su ogni piattaforma.

## Come si usa

1. **Apri documento…** (o trascina il file sulla finestra). L'analisi parte da sola.
2. Rivedi la tabella **Dati trovati**:
   - doppio clic sulla colonna ✓ (o `Spazio`) per attivare/disattivare un dato;
   - doppio clic sul testo per scrivere una sostituzione personalizzata;
   - clic destro → cambia categoria, *Non anonimizzare mai*, *Anonimizza sempre*;
   - `Canc` per togliere una riga.
3. Se manca qualcosa: **seleziona il testo nell'anteprima → clic destro → Anonimizza come…**
4. **Anonimizza e salva…** Il file prodotto viene riletto e il programma segnala
   se qualche dato attivo è ancora presente.

## Cosa riconosce

| Categoria | Esempi |
|---|---|
| Persone | `Mario ROSSI`, `Avv. Mario Rossi`, `Ms Anna Neri`, cognome da solo, `M. Rossi` |
| Codici fiscali | anche con spazi: `RSS MRA 80A01 L219X` |
| Partite IVA | con prefisso "P.IVA", oppure 11 cifre con cifra di controllo valida |
| Email / PEC, Telefoni / Fax | `(+39) 011.123.45.67`, `347 123 4567`, `0044…` (date e numeri di sentenza esclusi) |
| Indirizzi | `Via Roma n. 10`, `Via Garibaldi n. 12 - 10121 - TORINO`, indirizzi NL/DE/UK/FR |
| IBAN | con verifica mod-97 |
| Date di nascita | solo quelle in contesto "nato/a … il" |
| Codici | numeri di prenotazione/pratica/cliente, PNR, e-ticket, targhe |
| Società, Siti web | disattivati di default (il GDPR tutela le persone fisiche) |

Ogni dato trovato viene sostituito **ovunque compaia** con la stessa etichetta, così il
documento resta leggibile: `[PERSONA_1]` è sempre la stessa persona.

Modalità di sostituzione: etichette (`[PERSONA_1]`, `[CF_1]`…), iniziali per le persone
(`M.R.`, uso tipico delle sentenze), oppure `[omissis]` per tutto.

## Cosa viene ripulito oltre al testo

- **Word:** corpo, tabelle, caselle di testo, intestazioni/piè di pagina, note, commenti,
  revisioni, collegamenti `mailto:`, testo alternativo delle immagini, autore e
  "ultima modifica di", autori di commenti e revisioni. La formattazione resta intatta
  anche quando un nome è spezzato in più "run" (grassetto parziale ecc.).
- **PDF:** redazione vera con PyMuPDF — il testo sotto il riquadro viene **rimosso** dal
  file (non solo coperto), così come la porzione di immagine sottostante; link,
  metadati e allegati incorporati vengono eliminati.

## Limiti da conoscere

- Il riconoscimento dei nomi è a regole (elenco di nomi propri + titoli come Avv., Sig.,
  Mr…). Nomi molto rari senza titolo possono sfuggire: aggiungili in **Eccezioni e nomi…**
  (colonna *Nomi propri in più*) oppure selezionandoli nell'anteprima.
- Il cognome da solo viene attribuito alla persona più citata con quel cognome
  (es. tre "Rossi" diversi → controlla nella tabella).
- PDF scansionati senza testo: serve prima un OCR (il programma lo segnala).
- Parole spezzate con trattino a fine riga nei PDF non vengono trovate: la verifica
  finale le segnala.
- La tabella delle corrispondenze (CSV) permette di de-anonimizzare il documento:
  tienila separata e protetta.

**Controlla sempre il risultato prima di condividerlo.** Lo strumento riduce il lavoro,
non sostituisce la revisione.

## Riga di comando

```bash
python cli.py atto.pdf                         # -> atto_anonimizzato.pdf
python cli.py atto.docx --mode iniziali --mappa
python cli.py atto.pdf --solo-analisi          # elenca i dati trovati senza salvare
```

## Struttura

```
app.py              interfaccia grafica
cli.py              uso da terminale
anon/detector.py    rilevamento (regex, validatori, euristica nomi, propagazione)
anon/lexicon.py     nomi propri, titoli, parole escluse, città
anon/model.py       entità, categorie, matcher, etichette
anon/docx_io.py     lettura/scrittura Word
anon/pdf_io.py      lettura/redazione PDF
anon/pipeline.py    carica → analizza → esporta → verifica
anon/selftest.py    autotest dell'eseguibile compilato
Anonimizzatore.spec ricetta PyInstaller (Windows e macOS)
build.bat           build Windows
build_mac.sh        build macOS (.app + .dmg)
.github/workflows/  build automatica Windows + macOS
tests/              test su dati inventati (python tests/test_detector.py)
```

Impostazioni (eccezioni, nomi extra, ultime opzioni) salvate in
`%APPDATA%\AnonimizzatoreDocumenti\settings.json` (Windows) o
`~/Library/Application Support/AnonimizzatoreDocumenti/settings.json` (macOS).
