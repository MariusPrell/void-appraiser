# Changelog

## 0.9.0
- The interface is now in **English** by default; **German** can be selected under File → Settings.
- Code, documentation and release notes are now in English.
- Existing settings are kept; key names from older versions are converted automatically.

## 0.8.0
- New name: **Void Appraiser** (previously "Warframe Helper", a name already used by other projects).
- Settings, inventory list and cache are taken over automatically on the first start.

## 0.7.0
- New **Inventory** tab: under Inventory → Prime Parts a red hint appears at the top. Insert reads all visible parts including their count; after scrolling, another press extends the list.
- Per part: platinum, ducats and **ducats per platinum** (from about 10, Baro Ki'Teer is worth it), plus totals. Counts can be edited with a double-click; built Warframe parts are marked as not tradeable.
- New **Drop search** tab in the official drop tables, also by location. Double-click a relic to see its contents and value.

## 0.6.0
- Much smaller packages: Windows 94 instead of 155 MB, Linux 115 instead of 203 MB.
- Own lean text recognition (same models, without OpenCV).
- More reliable screen detection.

## 0.5.0
- New **Overview** tab: day cycles (Plains of Eidolon, Orb Vallis, Cambion Drift, Zariman, Duviri), void fissures with a filter for normal, Steel Path and Void Storm, and alerts, each with time left.
- When a dialog or reward screen is detected, the window switches to the relic view automatically.

## 0.4.3
- Ultrawide support (21:9, 32:9): detection follows the way the game interface sticks to the screen edges.

## 0.4.2
- Relic selection during endless missions (survival etc.) is detected.
- The overlay on the reward screen no longer flickers.

## 0.4.1
- Prices are requested up to three times on errors; missing prices are marked ("Loading prices …").

## 0.4.0
- First packages for Windows and Linux, MIT license.

## 0.3.0
- Overlay on top of the game: prices below the reward cards, relic info at the equip dialog. Clicks pass through and the game keeps the focus.

## 0.2.0
- Screen detection for the reward screen and the equip dialog, key for a manual scan, settings.

## 0.1.0
- Relic preview from the Warframe log with prices from warframe.market.
