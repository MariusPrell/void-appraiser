# Warframe Helper

Zeigt den Platin-Wert von Void-Relikt-Belohnungen. Preise von [warframe.market](https://warframe.market), Relikt-Inhalte von [drops.warframestat.us](https://drops.warframestat.us).

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
- fragt öffentliche Web-APIs ab

Es wird **nie**: Spielspeicher lesen, Spieldateien ändern, Eingaben ans Spiel senden oder automatisieren, Netzwerkverkehr des Spiels mitlesen. Änderungen, die gegen diese Regeln verstoßen, gehören nicht in dieses Projekt.
