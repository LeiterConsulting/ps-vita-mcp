# Build, pair and connect

This guide covers DevLoop alone. For background status, screen readback, managed files and synthetic input as well, follow [the complete modded-Vita baseline setup](GETTING-STARTED.md).

The initial host qualification uses Windows, PowerShell 7, Python 3.13 and Docker Desktop running Linux containers. Other hosts are not yet qualified. A homebrew-enabled Vita is needed to install the app; the tested prototype device runs firmware 3.65. This guide does not change firmware or install homebrew support.

The source builds experimental candidate **01.03**, title ID **CHRS00003**. Its device qualification is pending. Keep a copy of a working package before updating an existing DevLoop installation.

## Build from a checkout

```powershell
git clone https://github.com/LeiterConsulting/ps-vita-mcp.git
cd ps-vita-mcp
.\Setup-DevLoop.ps1
.\Build-DevLoop.ps1
```

If `python` is not your Python 3.13 interpreter, pass its executable to `Setup-DevLoop.ps1 -Python <path>`. Setup creates this checkout's `.venv-devloop` and installs the locked dependencies. Start Docker Desktop before building. The first build needs network access to retrieve the digest-pinned SDK image; containers run with networking disabled.

The full build runs native host tests with AddressSanitizer/UndefinedBehaviorSanitizer, the revision-publication regression check, MCP stdio fixtures, artwork checks, an ARM build and a local FTP fixture. No physical device is contacted by the build. `-SkipTests` is available for iteration but does not establish test acceptance.

Outputs:

- `dist/devloop/vita_devloop.vpk`: experimental installable package.
- `dist/devloop/SHA256SUMS.txt`: package SHA-256.
- `dist/devloop/build-report.json`: package identity, toolchain and source hashes.
- `evidence/devloop/`: local test logs, excluded from Git.

## First installation and pairing

1. Open the Vita file manager and enable USB storage. Identify its actual Windows drive letter.
2. From this checkout, run `Stage-DevLoop.ps1 -DriveLetter F`, replacing `F` with that letter. The helper checks USB disk identity, Vita storage layout, space and package hashes. If DevLoop is already installed, `-AllowUpdate` explicitly permits staging an update.
3. The helper creates a private random pairing token and copies `bridge.cfg` to `ux0:data/vita-devloop/`. It stages the VPK under the path printed by the command. A different existing pairing token is preserved and causes staging to stop for review.
4. Safely disconnect USB storage, then install the staged VPK in the Vita file manager. Installation is manual.
5. Open Vita DevLoop with Wi-Fi enabled. Set the desktop address using the IPv4 address shown on its display:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure.py <Vita-IPv4-address>
.\.venv-devloop\Scripts\python.exe bridge\call_tool.py vita_status
```

Replace angle-bracket placeholders with real values. DevLoop's HTTP port is 17865. Pairing files live in `.devloop-private/`, which is excluded from Git. Keep these files private. Requests authenticate with the pairing token over unencrypted LAN HTTP; use a trusted local network.

An unavailable device usually needs DevLoop opened in the foreground and Wi-Fi checked. An authentication error needs the desktop and device pairing files checked. After a timed-out change, read status before attempting another mutation.

## Connect an MCP client

Configure your client's stdio server with the **absolute** executable and script paths in this checkout. For clients that accept `mcpServers` JSON, the shape is:

```json
{
  "mcpServers": {
    "ps-vita": {
      "command": "C:/path/to/ps-vita-mcp/.venv-devloop/Scripts/python.exe",
      "args": ["C:/path/to/ps-vita-mcp/bridge/server.py"]
    }
  }
}
```

Replace the paths with your checkout. The bridge finds its private configuration relative to its own source directory, so a client's working directory is not significant. `VITA_DEVLOOP_CONFIG` and `VITA_DEVLOOP_FTP_CONFIG` can select alternate private configuration files. Exact client configuration screens and formats vary.

The bridge exposes [ten tools](TOOLS.md), `vita://scripting`, and starter examples at `vita://experiments/bounce` and `vita://experiments/input_scope`.

## Run an example

With DevLoop open and paired:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\bounce.lua --resume --capture
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\input_scope.lua --resume --capture
```

Use `--watch` to push each saved edit while that command runs in the foreground. Ctrl+C stops watching. A failed content hash is reported once, without automatic retry. Source files remain on the desktop; current and rollback Lua states on the Vita are RAM-only. [Scripting and recovery](../SCRIPTING.md).

## Stage later native updates over Wi-Fi

Exit DevLoop and open the Vita file manager's FTP server. Use the address and port it reports, which are separate from DevLoop's HTTP service:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure_ftp.py <Vita-IPv4-address>:<FTP-port>
$build = Get-Content .\dist\devloop\build-report.json -Raw | ConvertFrom-Json
$arguments = @{ expected_sha256 = $build.package.sha256 } | ConvertTo-Json -Compress
.\.venv-devloop\Scripts\python.exe bridge\call_tool.py vita_stage_package --arguments $arguments
```

The tool validates the selected local DevLoop VPK, uploads to a fresh inbox, verifies a temporary-file read-back, renames it and verifies the final-file read-back. Install the returned VPK path manually. Failed uploads are not replayed automatically. This uploader stages DevLoop packages; a general project registry is a future milestone.

## Device acceptance

Host tests and package verification do not certify an installed candidate. The separate `bridge/prove_device.py`, `bridge/prove_scripts.py` and `bridge/prove_upload.py` helpers perform live actions when explicitly run. The script proof loads and changes experiments; the upload proof stages the selected package. Review their scope and coordinate device availability before running them.

For 01.03, repeat both examples, visible editing, recovery and capture on the installed device, then verify physical input, clean exit and sleep/return. Record the exact package hash with the observations. [Acceptance gates](VALIDATION.md).
