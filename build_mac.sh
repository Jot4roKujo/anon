#!/usr/bin/env bash
# Crea dist/Anonimizzatore.app e dist/Anonimizzatore-macOS-<arch>.dmg
# Uso (dal Terminale, nella cartella del progetto):   ./build_mac.sh
# Con un Python specifico:                            PYTHON=/usr/local/bin/python3.12 ./build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Questo script va eseguito su macOS." >&2
  exit 1
fi

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null; then
  echo "Python non trovato. Installalo da https://www.python.org/downloads/macos/ e riprova." >&2
  exit 1
fi

# Serve un Python con Tk 8.6 o successivo. Il python3 di Apple (/usr/bin/python3) ha un
# Tk vecchio e instabile; quello di Homebrew non ha Tk se non si installa python-tk.
if ! "$PY" - <<'EOF'
import sys, tkinter
ok = tkinter.TkVersion >= 8.6 and sys.version_info >= (3, 10)
print(f"Python {sys.version.split()[0]}  ·  Tk {tkinter.TkVersion}  ·  {sys.executable}")
sys.exit(0 if ok else 1)
EOF
then
  cat >&2 <<'EOF'

Questo Python non ha tkinter (o ha un Tk troppo vecchio).
Soluzioni:
  • consigliata: installa Python da https://www.python.org/downloads/macos/
    e rilancia con  PYTHON=/usr/local/bin/python3.12 ./build_mac.sh
  • con Homebrew:  brew install python@3.12 python-tk@3.12
EOF
  exit 1
fi

# ambiente isolato per la build
rm -rf .venv-build
"$PY" -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --clean Anonimizzatore.spec

APP="dist/Anonimizzatore.app"
ARCH="$(python -c 'import platform; print(platform.machine())')"   # arm64 / x86_64
DMG="dist/Anonimizzatore-macOS-${ARCH}.dmg"

# .dmg con il collegamento ad Applicazioni (trascina e installa)
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
for attempt in 1 2 3; do       # hdiutil a volte risponde "Resource busy": si riprova
  if hdiutil create -volname "Anonimizzatore" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null; then
    break
  fi
  sleep 3
done
rm -rf "$STAGE"
deactivate

echo
echo "Fatto:"
echo "  $APP"
echo "  $DMG   (architettura: $ARCH)"
