# Void Appraiser

Shows you at a glance what your void relics and prime parts are worth in Warframe: right on top of the game and in a separate window. For Windows and Linux.

> Not an official product and not affiliated with Digital Extremes. Warframe is a trademark of Digital Extremes Ltd.

## Features

- **Prices on the reward screen:** At the end of a fissure, platinum and ducats appear below every card, and the most valuable part is highlighted in green.
- **Relic preview:** When you equip a relic, you see all possible parts with chance, price and the average value per opening.
- **Inventory:** Under Inventory → Prime Parts it reads your parts including their count and shows **ducats per platinum**. That tells you what to give to Baro Ki'Teer and what to sell.
- **Overview:** Day cycles of the open worlds, all void fissures (normal, Steel Path, Void Storm) and alerts with time left.
- **Drop search:** Where does a part drop? Search the official drop tables, e.g. "Gauss Neuroptics".

The interface is available in English and German (File → Settings). Prices come from [warframe.market](https://warframe.market), drop data and the world state from [warframestat.us](https://warframestat.us).

## Installation

Download the package for your system from the **[latest release](https://github.com/MariusPrell/void-appraiser/releases/latest)**. You do not need to install Python.

**Windows**
1. Extract `void-appraiser-windows.zip`.
2. Start `void-appraiser.exe` in the `void-appraiser` folder.
3. If Windows warns you ("Windows protected your PC"): "More info" → "Run anyway". The program is not signed.

**Linux**
```bash
tar -xzf void-appraiser-linux.tar.gz
./void-appraiser/void-appraiser
```
Hyprland and X11 are supported. On Hyprland, `grim` is needed for screenshots.

**In-game requirements**
- Language **English**
- Display mode **borderless fullscreen** or windowed, so the overlay is visible
- Any resolution and aspect ratio (16:9, 21:9, 32:9)

## Usage

- The reward screen, the equip dialog and the inventory are detected automatically while Warframe is in the foreground.
- **Insert** triggers a scan by hand; in the inventory it reads your parts. Then scroll and press it again, the list is extended.
- Under **File → Settings** you can change the language, key, scan interval, overlay and screen.

## Safety

Void Appraiser only works from the outside, like WFInfo. It reads the log file `EE.log` that Warframe writes anyway, takes screenshots and queries public websites. It **never** reads the game's memory, **never** changes game files and **never** sends input to the game. As with any third-party tool, there is still no guarantee against bans.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest pyinstaller
.venv/bin/void-appraiser            # run
.venv/bin/python -m pytest          # tests
.venv/bin/pyinstaller packaging/void-appraiser.spec --noconfirm   # build a package
```
GitHub Actions builds the Windows and Linux packages for every version tag (`v*`). What changed in each version is listed in the [CHANGELOG](CHANGELOG.md) and on the releases. Contributions are welcome; code, comments and commit messages are in English, the interface texts are translated in `void_appraiser/i18n_de.py`.

## License

[MIT](LICENSE). The packages include software from other projects, among them Qt (LGPL-3.0), ONNX Runtime (MIT) and the PaddleOCR models (Apache-2.0). All license texts are included in every package as `THIRD-PARTY-LICENSES.txt`.

Developed with the help of Claude (Anthropic). Up to version 0.7 the project was called "Warframe Helper".
