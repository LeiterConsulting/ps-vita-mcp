# Third-party notices

Original DevLoop, Resident, Control, Inspector code and documentation use the [project MIT license](LICENSE). That license does not replace dependency licenses.

## Vendored Lua

`third_party/lua-5.4.9/` contains the official Lua 5.4.9 source, its README and license-bearing readme. Lua is copyright 1994–2026 Lua.org, PUC-Rio and is distributed under MIT. The full notice is also included in [the VPK license file](assets/devloop-licenses.txt).

[Lua provenance](third_party/lua-5.4.9/provenance.json) records the archive URL and SHA-256. Host and Vita builds use this same source. [Upstream license](https://www.lua.org/license.html).

## Build and runtime dependencies

The native build uses the image pinned in [toolchain.lock.json](toolchain.lock.json), from [VitaSDK's Docker project](https://github.com/vitasdk/docker). Native dependencies include [libvita2d](https://github.com/xerpi/libvita2d), [FreeType](https://freetype.org/), [libpng](https://www.libpng.org/pub/png/libpng.html), JPEG and zlib from that SDK. They retain their upstream notices and licenses.

Resident, Control and Inspector use VitaSDK's user/kernel import stubs. Control and Inspector also link the SDK's [taiHEN](https://github.com/yifanlu/taiHEN) user library for explicit module loading.

## Adapted input hooks

Control input hooks and emulation derive from the MIT-licensed [vitacompanion kernel](https://github.com/devnoname120/vitacompanion/tree/d46772344d926e6765943703adf1a1518c20e10e/kernel), pinned to commit `d46772344d926e6765943703adf1a1518c20e10e`. Its full license is retained in [LICENSE.vitacompanion](resident/control/LICENSE.vitacompanion). Control does not import that project's FTP/command daemon or keep-awake behavior. No USB video driver or proprietary game data is included.

The desktop environment installs the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Pillow](https://github.com/python-pillow/Pillow) and their dependencies from the versions in `bridge/requirements-lock.txt`. Those packages are installed locally, rather than vendored into this repository.

The source import includes Lua's complete notice and the project's MIT text in generated packages. A complete notice audit for every linked SDK library is a remaining binary-release task; the current source candidate is not a prebuilt public release.
