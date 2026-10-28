# -*- mode: python ; coding: utf-8 -*-
# Ricetta PyInstaller unica per Windows e macOS:
#   python -m PyInstaller --noconfirm --clean Anonimizzatore.spec
#
#   Windows -> dist/Anonimizzatore.exe      (un solo file)
#   macOS   -> dist/Anonimizzatore.app      (bundle; poi build_mac.sh crea il .dmg)
#
# La build va fatta sul sistema di destinazione: PyInstaller non compila per Mac da
# Windows (né viceversa), e un .app compilato su Mac Intel/Apple Silicon gira solo su
# quell'architettura (su Apple Silicon anche la versione Intel, tramite Rosetta).
import sys

from PyInstaller.utils.hooks import collect_all

IS_MAC = sys.platform == "darwin"
NAME = "Anonimizzatore"
VERSION = "1.0"

datas, binaries, hiddenimports = [], [], []
try:  # trascinamento file (facoltativo)
    d, b, h = collect_all("tkinterdnd2")
    datas, binaries, hiddenimports = datas + d, binaries + b, hiddenimports + h
except Exception:
    pass

a = Analysis(
    ["app.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # pymupdf.layout (pacchetto pymupdf_layout) carica modelli ONNX che PyInstaller non
    # include e farebbe crashare l'avvio; al programma non serve.
    excludes=["pymupdf.layout", "onnxruntime"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    # Su macOS un .app "a cartella" (onedir): si avvia subito e Gatekeeper lo gestisce
    # meglio dell'opzione --onefile, che PyInstaller sconsiglia per i bundle.
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=NAME,
        console=False,
        argv_emulation=False,      # i file aperti dal Finder arrivano a Tk (::tk::mac::OpenDocument)
        target_arch=None,          # architettura del Python usato per la build
        codesign_identity=None,    # firma ad-hoc (vedi README per Developer ID)
        entitlements_file=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=None,
        bundle_identifier="it.anonimizzatore.documenti",
        version=VERSION,
        info_plist={
            "CFBundleName": NAME,
            "CFBundleDisplayName": "Anonimizzatore Documenti",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.productivity",
            # compare in "Apri con" per PDF e Word, e accetta file trascinati sull'icona
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "Documento PDF", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate", "LSItemContentTypes": ["com.adobe.pdf"]},
                {"CFBundleTypeName": "Documento Word", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["org.openxmlformats.wordprocessingml.document"]},
            ],
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=NAME,
        console=False,
        upx=False,
    )
