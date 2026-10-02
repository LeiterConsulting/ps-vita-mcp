"""Vendor a checksum-pinned official Lua release for identical host/Vita builds."""
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "5.4.9"
SHA256 = "2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6"
URL = f"https://www.lua.org/ftp/lua-{VERSION}.tar.gz"
target = ROOT / "third_party" / f"lua-{VERSION}"
with urllib.request.urlopen(URL, timeout=25) as response:
    data = response.read(1024 * 1024)
assert hashlib.sha256(data).hexdigest() == SHA256, "Official Lua archive checksum mismatch"
target.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
    for entry in archive.getmembers():
        parts = Path(entry.name).parts
        assert parts[0] == f"lua-{VERSION}" and ".." not in parts
        if entry.isfile() and (parts[1:2] == ("src",) or entry.name.endswith(("/README", "/doc/readme.html"))):
            destination = target.joinpath(*parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(entry).read())
(target / "provenance.json").write_text(json.dumps({"version": VERSION, "source": URL, "archiveSha256": SHA256, "checksumSource": "https://www.lua.org/ftp/", "license": "MIT; see doc/readme.html and source headers"}, indent=2) + "\n")
print(f"PASS official Lua {VERSION} source archive SHA-256; vendored under {target}")
