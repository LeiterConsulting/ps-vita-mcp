"""Create pairing configuration or set the device address; never print the token."""
import argparse
import ipaddress
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("address", nargs="?", help="Local Wi-Fi IPv4 address shown on Vita DevLoop")
args = parser.parse_args()
folder = ROOT / ".devloop-private"
folder.mkdir(exist_ok=True)
path = folder / "config.json"
config = json.loads(path.read_text()) if path.exists() else {"host": "", "port": 17865, "token": secrets.token_hex(16)}
if args.address:
    address = ipaddress.IPv4Address(args.address)
    if not address.is_private or address.is_multicast or address.is_unspecified:
        parser.error("Use a local Wi-Fi IPv4 address")
    config["host"] = str(address)
path.write_text(json.dumps(config, indent=2) + "\n")
(folder / "bridge.cfg").write_text(config["token"] + "\n")
print("Pairing configuration ready; token kept private.")
print("Device address: " + (config["host"] or "pending - read the address shown on Vita DevLoop"))
