# three.js (vendored)

Third-party code, copied unchanged so the 3D stage works offline. Do not edit these files; replace them with a newer release instead.

| | |
| --- | --- |
| Project | three.js, <https://threejs.org/> (<https://github.com/mrdoob/three.js>) |
| Version | 0.170.0 (r170, npm, published 2024-10-31) |
| Licence | MIT, full text in [LICENSE](LICENSE) |
| Source | `https://registry.npmjs.org/three/-/three-0.170.0.tgz` |
| Checksum | npm integrity `sha512-FQK+LEpYc0fBD+J8g6oSEyyNzjp+Q7Ks1C568WWaoMRLW+TkNNWmenWeGgJjV105Gd+p/2ql1ZcjYvNiPZBhuQ==` (verified) |
| Files | `build/three.module.min.js` (a single ES module, no imports) and `LICENSE` |
| Changes | None |

r170 is the last release whose `three.module.js` is one self-contained file; later releases split it into `three.core.js` plus a module that imports it.

## Updating

1. Download the new tarball from npm and check its `dist.integrity` against the registry.
2. Copy the module build and `LICENSE` over these files (for r171+ also copy `three.core.min.js`).
3. Update the version, date and checksum above, and in the root README's third-party list.
4. Run `uv run codezoo serve --open`, switch the stage to 3D and check that a run animates.
