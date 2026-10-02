"""Store the user-reported file manager FTP endpoint separately from HTTP pairing."""
import argparse
import json
from pathlib import Path
from ftp_staging import endpoint

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("address", help="IPv4:port displayed by the file manager")
args = parser.parse_args()
host, separator, port = args.address.rpartition(":")
if not separator:
    parser.error("Supply IPv4:port")
target = ROOT / ".devloop-private/ftp.json"
target.parent.mkdir(exist_ok=True)
temporary = target.with_suffix(".tmp")
try:
    temporary.write_text(json.dumps({"host": host, "port": int(port)}, indent=2) + "\n")
    checked = endpoint(temporary)
    temporary.replace(target)
finally:
    temporary.unlink(missing_ok=True)
print(f"FTP configured: {checked['host']}:{checked['port']}. HTTP pairing is unchanged.")
