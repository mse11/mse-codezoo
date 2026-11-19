# Blockly (vendored)

Third-party code, copied unchanged so the web UI works offline. Do not edit these files; replace them with a newer release instead.

| | |
| --- | --- |
| Project | Blockly, <https://github.com/RaspberryPiFoundation/blockly> (originally by Google, now maintained by the Raspberry Pi Foundation) |
| Version | 13.3.0 (npm, published 2026-09-10) |
| Licence | Apache License 2.0, full text in [LICENSE](LICENSE) |
| Source | `https://registry.npmjs.org/blockly/-/blockly-13.3.0.tgz` |
| Checksum | npm integrity `sha512-qAHFGMGTSF67Lupr3pjZz9LQu4JCFdN76CMZxegBKiveZreK08yXhaCz0g9q9/xe5GEdoeFT3POAlQavPIRPEw==` (verified) |
| Files | `blockly.min.js` and `media/` from the package root, plus `LICENSE` |
| Changes | None |

CodeZoo's own code is MIT-licensed; these files stay under Apache-2.0.

## Updating

1. Download the new tarball from npm and check its `dist.integrity` against the registry.
2. Copy `package/blockly.min.js`, `package/LICENSE` and `package/media/*` over these files.
3. Update the version, date and checksum above, and in the root README's third-party list.
4. Run `uv run codezoo serve --open` and check that blocks still load, drag and highlight.
