# Third-party notices

The repository's MIT license applies to original application code and scripts only. It does not replace licenses or ownership of dependencies, models, artwork, trademarks, or other third-party material.

## Libraries

`DEPENDENCIES.json` records the pinned build environment and links to the license files retained in `LICENSES/`. Preserve relevant notices when distributing the application and bundled libraries.

- Python: PSF license and notices in `LICENSES/Python-LICENSE.txt`.
- PySide6/Shiboken6/Qt: see their retained LGPL/GPL/commercial notices. The application uses dynamically linked Qt libraries and does not prevent users from replacing them. Corresponding upstream source is available at https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://code.qt.io/cgit/qt/qtbase.git/ .
- CTranslate2: see `LICENSES/ctranslate2/` and https://github.com/OpenNMT/CTranslate2 .
- SentencePiece: see `LICENSES/sentencepiece/` and https://github.com/google/sentencepiece .
- PyWinRT: see retained package notices and https://github.com/pywinrt/pywinrt .
- PyInstaller build tool: GPL with bootloader exception; see retained license and https://github.com/pyinstaller/pyinstaller .
- HTTPX and other packages: see the exact per-package entries in `DEPENDENCIES.json`.

## OPUS model

`models/opus` contains the English-to-Vietnamese CTranslate2 INT8 model from `dekthedev/opus-mt-en-vi-ct2-int8`, revision `c22547827b876e8ee939d6a9363965e5c9f769e1`, derived from Helsinki-NLP/opus-mt-en-vi. The published conversion and upstream cards declare Apache-2.0. Sources, file hashes, tokenizer conventions, and revisions are retained in `models/opus/provenance.json`. Retain the Apache-2.0 notice and provenance with redistributed weights; MIT does not relicense these weights.

## Artwork and NIKKE

The icon and interface artwork were supplied by the requesting user. Character images, game material, and NIKKE names/trademarks remain owned by their respective rightsholders. No rights to this material are granted by the MIT license. This community tool is not affiliated with or endorsed by the game publisher. Review permissions before redistributing or using these assets commercially.

Music, clone-voice audio, narration-provider credentials, and tutorial project files are not part of this repository.
