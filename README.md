# Warframe Helper

Zeigt den Platin-Wert von Void-Relikt-Belohnungen. Preise von [warframe.market](https://warframe.market), Relikt-Inhalte von [drops.warframestat.us](https://drops.warframestat.us).

> **Hinweis:** Kein offizielles Produkt, nicht mit Digital Extremes verbunden. Warframe ist eine Marke von Digital Extremes Ltd.

Mit Hilfe von Claude (Anthropic) entwickelt. Lizenz: [MIT](LICENSE).

## Herunterladen
Fertige Pakete für Windows und Linux: [neuestes Release](https://github.com/MariusPrell/warframe-helper/releases/latest).
- **Windows:** `warframe-helper-windows.zip` entpacken, `warframe-helper.exe` im Ordner `warframe-helper` starten. Beim ersten Start warnt Windows eventuell („Windows hat den PC geschützt“), weil das Programm nicht signiert ist: „Weitere Informationen“ → „Trotzdem ausführen“.
- **Linux:** `warframe-helper-linux.tar.gz` entpacken, `warframe-helper/warframe-helper` starten.
- Voraussetzungen: Warframe auf **Englisch** und im Modus **randloses Vollbild** oder Fenster (für das Overlay). Jede Auflösung und jedes Seitenverhältnis (16:9, 21:9, 32:9) wird unterstützt.

## Stand (0.5.0)
- **Tab „Overview“:** Tageszeiten (Plains of Eidolon, Orb Vallis, Cambion Drift, Zariman, Duviri), alle Void Fissures mit Filter für Normal, Steel Path und Void Storm sowie die Alerts, jeweils mit Restzeit. Quelle: Fan-API [api.warframestat.us](https://api.warframestat.us), Abruf jede Minute.
- Die Relikt-Ansicht ist jetzt der Tab „Relikte“. Sie öffnet sich automatisch, sobald ein Ausrüsten-Dialog oder Belohnungsbildschirm erkannt wird.

## Stand (0.4.0)
- Fertige Pakete für Windows und Linux, gebaut von GitHub Actions.

## Stand (0.3.0, Stufe 3)
- **Overlay über dem Spiel:** Unter jeder Belohnungskarte stehen Platin und Ducats, das wertvollste Teil ist grün markiert. Beim Ausrüsten-Dialog erscheint eine Kurzinfo (Dauer einstellbar, Standard 5 s) zum Relikt (Erwartungswert, bestes Teil). In den Einstellungen abschaltbar.
- Das Overlay lässt Klicks durch und nimmt dem Spiel nicht den Fokus.
- Hyprland: Platzierung per `hyprctl dispatch` (Lua-Syntax ab 0.55, klassische Syntax ungetestet). Im Leerlauf parkt das Overlay als 1×1-Pixel-Fenster auf einem anderen Monitor, damit das Spiel Direct Scanout behält.
- Windows: rahmenloses Fenster im Vordergrund. Warframe muss dafür im Modus „Randloses Vollbild“ oder „Fenster“ laufen, nicht im exklusiven Vollbild (ungetestet).

## Stand (0.2.0, Stufe 2)
- **Bildschirmerkennung:** Alle 1,5 s (einstellbar, abschaltbar) wird geprüft, ob der Belohnungsbildschirm oder der Ausrüsten-Dialog zu sehen ist. Das geht nur, solange Warframe im Vordergrund ist. Die Teile zur Auswahl erscheinen oben mit Preis, das wertvollste ist markiert.
- **Manueller Scan:** per Taste (einstellbar, Standard: Einfg) oder mit dem Knopf „Jetzt scannen“.
- Texterkennung mit RapidOCR, läuft lokal und braucht keine Installation im System.
- Linux: Hyprland (grim, hyprctl) oder X11. Windows: mss und die Win32-API.
- Einstellungen unter Datei → Einstellungen. Zur Fehlersuche werden erkannte Bildschirme in `~/.cache/warframe-helper/scans` gespeichert (abschaltbar).

## Stand (0.1.0, Stufe 1)
- Liest das Warframe-Log (`EE.log`) mit und erkennt das ausgerüstete Relikt samt Veredelung.
- Zeigt die möglichen Teile mit Chance, Platin (Median der 5 günstigsten Angebote von Spielern, die online sind), günstigstem Angebot und Ducats sowie den Erwartungswert pro Öffnung.
- Erkennt, wann der Belohnungsbildschirm offen ist (Grundlage für die OCR in Stufe 2).
- Relikte lassen sich auch von Hand suchen.
- Nur mit englischem Spielclient (das Log ist sprachabhängig).

## Pakete bauen (Stufe 4)
Fertige Programme ohne Python-Installation, gebaut mit PyInstaller (`packaging/warframe-helper.spec`):
```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller packaging/warframe-helper.spec --noconfirm --distpath build/dist --workpath build/work
build/dist/warframe-helper/warframe-helper --selftest tests/fixtures/belohnung-3-karten.png
```
Windows-Pakete baut GitHub Actions (`.github/workflows/build.yml`): bei einem Tag `v*` oder von Hand. Ergebnis: `warframe-helper-windows.zip` und `warframe-helper-linux.tar.gz` (gepackt etwa 200 MB).

`--selftest BILD` prüft die Texterkennung auf einem Bildschirmfoto ohne Fenster. Die Testbilder in `tests/fixtures/` enthalten nur Kopfzeile, Kartennamen und Dialogtext, keine Spielernamen.

## Starten
```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
.venv/bin/warframe-helper           # optional: --log /pfad/zu/EE.log
```
Das Log wird automatisch gesucht: unter Windows in `%LOCALAPPDATA%\Warframe\EE.log`, unter Linux in allen Steam-Bibliotheken (Proton-Prefix 230410).

Cache: `~/.cache/warframe-helper` bzw. `%LOCALAPPDATA%\warframe-helper`.

## Tests
```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest
```

## Grundsätze (Bann-Sicherheit)
Das Programm arbeitet nur passiv von außen, wie WFInfo:
- liest nur die Textdatei `EE.log`, die das Spiel ohnehin schreibt
- macht nur Bildschirmfotos (wie ein Streaming-Programm)
- hört auf eine Taste für den manuellen Scan, sendet aber nie Tasten
- fragt öffentliche Web-APIs ab

Es wird **nie**: Spielspeicher lesen, Spieldateien ändern, Eingaben ans Spiel senden oder automatisieren, Netzwerkverkehr des Spiels mitlesen. Änderungen, die gegen diese Regeln verstoßen, gehören nicht in dieses Projekt.

## Fremdlizenzen
Die fertigen Pakete enthalten Bibliotheken anderer Projekte, u. a. Qt/PySide6 (LGPL-3.0), RapidOCR (Apache-2.0), ONNX Runtime (MIT), OpenCV (Apache-2.0), NumPy (BSD), Pillow (MIT-CMU), mss (MIT) und pynput (LGPL-3.0). Die vollständige Liste mit den Lizenztexten liegt jedem Paket als `THIRD-PARTY-LICENSES.txt` bei und wird beim Bauen erzeugt (`packaging/licenses.py`).
