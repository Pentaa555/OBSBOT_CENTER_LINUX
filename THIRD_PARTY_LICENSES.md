# Third-party assets and licenses

## OBSBOT Center UI assets (LGPL-3.0)

The icon files under `app/resources/images/` and the reference theme
`app/resources/themes/obsbot-center-dark.reference.qss` were extracted from the
official **OBSBOT Center** desktop application, which is distributed under the
**GNU Lesser General Public License v3.0 (LGPL-3.0)**.

OBSBOT Center is powered by Qt (also LGPLv3):
https://download.qt.io/official_releases/qt/6.5/6.5.2/single/qt-everywhere-src-6.5.2.tar.xz

Files reused:

- `app/resources/images/*.png` — UI icons (gimbal, tracking, playback,
  camera controls). Used as-is.
- `app/resources/themes/obsbot-center-dark.reference.qss` — kept for reference
  only. It is **not** applied at runtime: it relies on OBSBOT's custom
  `RMTheme` selector and `themeID` widget properties that plain Qt does not
  interpret.
- `app/resources/locale-reference/es-ES.ini`, `en-US.ini` — OBSBOT's official
  terminology, kept as a translation reference. Not loaded at runtime.

## Fonts

### Inter (SIL Open Font License 1.1)

The UI typeface is **Inter** by Rasmus Andersson, distributed under the
**SIL Open Font License, Version 1.1** (https://openfontlicense.org):

- `app/resources/fonts/Inter-Regular.ttf` — base / secondary text.
- `app/resources/fonts/Inter-Medium.ttf` — buttons and tabs.
- `app/resources/fonts/Inter-SemiBold.ttf` — titles and active/selected items.

The OFL permits use, embedding, and redistribution of the font, including
within software. The font itself must not be sold on its own and must retain
its license.

A full copy of the LGPL-3.0 license text is available in the OBSBOT Center
distribution and at https://www.gnu.org/licenses/lgpl-3.0.txt

Per LGPL-3.0, these assets may be used, modified, and redistributed under the
same license terms. This notice provides the required attribution.
