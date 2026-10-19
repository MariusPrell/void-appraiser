# Void Appraiser

Zeigt dir in Warframe auf einen Blick, was deine Void-Relikte und Prime-Teile wert sind: direkt über dem Spiel und in einem eigenen Fenster. Für Windows und Linux.

> Kein offizielles Produkt, nicht mit Digital Extremes verbunden. Warframe ist eine Marke von Digital Extremes Ltd.

## Was es kann

- **Preise auf dem Belohnungsbildschirm:** Am Ende einer Fissure stehen Platin und Ducats unter jeder Karte, das wertvollste Teil ist grün markiert.
- **Relikt-Vorschau:** Beim Ausrüsten eines Relikts siehst du alle möglichen Teile mit Chance, Preis und dem Durchschnittswert pro Öffnung.
- **Inventar:** Unter Inventar → Prime Parts liest es deine Teile samt Anzahl ein und zeigt **Ducats pro Platin**. So siehst du, was du besser bei Baro Ki'Teer abgibst und was du verkaufen solltest.
- **Overview:** Tageszeiten der offenen Welten, alle Void Fissures (Normal, Steel Path, Void Storm) und Alerts mit Restzeit.
- **Drop-Suche:** Wo gibt es ein Teil? Suche in den offiziellen Drop-Tabellen, z. B. „Gauss Neuroptics“.

Preise kommen von [warframe.market](https://warframe.market), Drop-Daten und Spielzustand von [warframestat.us](https://warframestat.us).

## Installation

Lade das passende Paket aus dem **[neuesten Release](https://github.com/MariusPrell/void-appraiser/releases/latest)** herunter. Python musst du nicht installieren.

**Windows**
1. `void-appraiser-windows.zip` entpacken.
2. Im Ordner `void-appraiser` die Datei `void-appraiser.exe` starten.
3. Falls Windows warnt („Windows hat den PC geschützt“): „Weitere Informationen“ → „Trotzdem ausführen“. Das Programm ist nicht signiert.

**Linux**
```bash
tar -xzf void-appraiser-linux.tar.gz
./void-appraiser/void-appraiser
```
Unterstützt werden Hyprland und X11. Unter Hyprland wird `grim` für Bildschirmfotos gebraucht.

**Voraussetzungen im Spiel**
- Sprache **Englisch**
- Anzeigemodus **randloses Vollbild** oder Fenster, damit das Overlay sichtbar ist
- Jede Auflösung und jedes Seitenverhältnis (16:9, 21:9, 32:9)

## Bedienung

- Das Programm erkennt Belohnungsbildschirm, Ausrüsten-Dialog und Inventar automatisch, solange Warframe im Vordergrund ist.
- **Einfg** löst einen Scan von Hand aus, im Inventar liest es damit die Teile ein. Danach scrollen und erneut drücken, die Liste wird ergänzt.
- Unter **Datei → Einstellungen** stellst du Taste, Scan-Abstand, Overlay und Bildschirm ein.

## Sicherheit

Void Appraiser arbeitet nur von außen, wie WFInfo. Es liest das Log `EE.log`, das Warframe ohnehin schreibt, macht Bildschirmfotos und fragt öffentliche Webseiten ab. Es liest **nie** den Spielspeicher, ändert **nie** Spieldateien und sendet **nie** Eingaben ans Spiel. Eine Garantie gegen Banns gibt es bei Fremdprogrammen trotzdem nicht.

## Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest pyinstaller
.venv/bin/void-appraiser            # starten
.venv/bin/python -m pytest          # Tests
.venv/bin/pyinstaller packaging/void-appraiser.spec --noconfirm   # Paket bauen
```
Die Pakete für Windows und Linux baut GitHub Actions bei jedem Versions-Tag (`v*`). Was sich je Version geändert hat, steht im [CHANGELOG](CHANGELOG.md) und bei den Releases.

## Lizenz

[MIT](LICENSE). Die Pakete enthalten Software anderer Projekte, u. a. Qt (LGPL-3.0), ONNX Runtime (MIT) und die PaddleOCR-Modelle (Apache-2.0). Alle Lizenztexte liegen jedem Paket in `THIRD-PARTY-LICENSES.txt` bei.

Mit Hilfe von Claude (Anthropic) entwickelt. Bis Version 0.7 hieß das Projekt „Warframe Helper“.
