# Warframe Helper

Zeigt den Platin-Wert von Void-Relikt-Belohnungen. Preise von [warframe.market](https://warframe.market), Relikt-Inhalte von [drops.warframestat.us](https://drops.warframestat.us).

## Stand (0.2.0, Stufe 2, im Test)
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
