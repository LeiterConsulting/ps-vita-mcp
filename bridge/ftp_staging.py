"""Stage the fixed, validated DevLoop artifact through the file manager's FTP."""
from __future__ import annotations
import ftplib
import hashlib
import io
import ipaddress
import json
import re
import struct
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MAX_PACKAGE = 8 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
PACKAGE_FILES = {
    "eboot.bin", "sce_sys/param.sfo", "sce_sys/icon0.png",
    "sce_sys/livearea/contents/bg.png", "sce_sys/livearea/contents/startup.png",
    "sce_sys/livearea/contents/template.xml",
}


def endpoint(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        host = ipaddress.IPv4Address(config["host"])
        port = config["port"]
        if (not (host.is_private or host.is_loopback) or host.is_unspecified
                or host.is_multicast or type(port) is not int or not 1 <= port <= 65535):
            raise ValueError("Invalid local FTP endpoint")
        user = config.get("username", "anonymous")
        password = config.get("password", "anonymous@")
        if any(not isinstance(value, str) or any(c in value for c in "\r\n\x00")
               for value in (user, password)):
            raise ValueError("Invalid FTP credentials")
        return {"host": str(host), "port": port, "username": user, "password": password}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError("FTP is not configured. Run bridge/configure_ftp.py with the file manager's displayed IPv4:port.") from error


def read_sfo(data: bytes) -> dict:
    magic, version, key_start, data_start, count = struct.unpack_from("<5I", data)
    if magic != 0x46535000 or version != 0x101 or not 0 < count <= 64:
        raise ValueError("Invalid SFO header")
    if not 20 + count * 16 <= key_start < data_start <= len(data):
        raise ValueError("Invalid SFO layout")
    result = {}
    for index in range(count):
        key_offset, fmt, length, maximum, value_offset = struct.unpack_from("<HHIII", data, 20 + index * 16)
        key_pos = key_start + key_offset
        if not key_start <= key_pos < data_start:
            raise ValueError("Invalid SFO key")
        key_end = data.index(b"\0", key_pos, data_start)
        key = data[key_pos:key_end].decode("utf-8")
        value_pos = data_start + value_offset
        if not length <= maximum or not data_start <= value_pos <= value_pos + maximum <= len(data):
            raise ValueError("Invalid SFO value")
        value = data[value_pos:value_pos + length]
        if key in result:
            raise ValueError("Duplicate SFO key")
        if fmt == 0x404 and length == 4:
            result[key] = struct.unpack("<I", value)[0]
        elif fmt == 0x204 and value.endswith(b"\0"):
            result[key] = value.rstrip(b"\0").decode("utf-8")
        else:
            raise ValueError("Unsupported SFO field")
    return result


def validate_package(package_path: Path, report_path: Path, expected_sha256: str) -> tuple[bytes, dict]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected_sha256 must be the package's lowercase SHA-256")
    if not 0 < package_path.stat().st_size <= MAX_PACKAGE:
        raise ValueError("DevLoop package exceeds the staging limit")
    # Hold the validated bytes for upload: replacement of the local file cannot change this attempt.
    data = package_path.read_bytes()
    if not 0 < len(data) <= MAX_PACKAGE:
        raise ValueError("DevLoop package exceeds the staging limit")
    digest = hashlib.sha256(data).hexdigest()
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))["package"]
    if digest != expected_sha256 or digest != report["sha256"] or len(data) != report["bytes"]:
        raise ValueError("DevLoop package, expected hash and build report do not match")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        required = PACKAGE_FILES | ({"licenses.txt"} if report["version"] >= "01.02" else set())
        if len(names) != len(required) or set(names) != required:
            raise ValueError("Unexpected DevLoop package entries")
        if sum(entry.file_size for entry in archive.infolist()) > MAX_UNPACKED:
            raise ValueError("DevLoop package expands beyond the staging limit")
        if archive.testzip() is not None or archive.read("eboot.bin")[:4] != b"SCE\0":
            raise ValueError("DevLoop ZIP or SELF is invalid")
        sfo = read_sfo(archive.read("sce_sys/param.sfo"))
    if (report["file"] != "vita_devloop.vpk" or report["titleId"] != "CHRS00003"
            or sfo.get("TITLE_ID") != "CHRS00003" or sfo.get("TITLE") != "Vita DevLoop"
            or sfo.get("CATEGORY") != "gd" or sfo.get("APP_VER") != report["version"]
            or not re.fullmatch(r"\d{2}\.\d{2}", report["version"])
            or type(sfo.get("PSP2_SYSTEM_VER")) is not int
            or not 0 <= sfo["PSP2_SYSTEM_VER"] <= 0x03650000):
        raise ValueError("DevLoop application ID, version or firmware does not match")
    return data, {"title_id": "CHRS00003", "version": report["version"], "bytes": len(data), "sha256": digest}


def enter_shared_directory(ftp: ftplib.FTP, name: str) -> None:
    try:
        ftp.cwd(name)
    except ftplib.error_perm as error:
        if not str(error).startswith("550"):
            raise
        ftp.mkd(name)
        ftp.cwd(name)


def verify_remote(ftp: ftplib.FTP, filename: str, package: dict) -> str:
    digest = hashlib.sha256()
    observed_size = 0

    def accept(block: bytes) -> None:
        nonlocal observed_size
        observed_size += len(block)
        if observed_size > package["bytes"]:
            raise ValueError("Remote package exceeded its expected size")
        digest.update(block)

    ftp.retrbinary("RETR " + filename, accept, blocksize=64 * 1024)
    observed_hash = digest.hexdigest()
    if observed_size != package["bytes"] or observed_hash != package["sha256"]:
        raise ValueError("FTP read-back size or SHA-256 does not match the package")
    return observed_hash


def stage_package(package_path: Path, report_path: Path, config_path: Path, expected_sha256: str) -> dict:
    data, package = validate_package(package_path, report_path, expected_sha256)
    config = endpoint(config_path)
    attempt = f"{package['version']}-{package['sha256'][:12]}-{uuid.uuid4().hex}"
    vita_dir = f"ux0:data/vita-devloop/inbox/{attempt}"
    state = "connecting"
    ftp = ftplib.FTP(timeout=10)
    try:
        ftp.connect(config["host"], config["port"])
        ftp.login(config["username"], config["password"])
        # Keep the passive data connection on the same host supplied by the user.
        ftp.trust_server_pasv_ipv4_address = False
        ftp.cwd("ux0:/data")
        enter_shared_directory(ftp, "vita-devloop")
        enter_shared_directory(ftp, "inbox")
        state = "creating fresh attempt directory"
        # A collision fails; never reuse or overwrite an existing attempt.
        ftp.mkd(attempt)
        ftp.cwd(attempt)
        if ftp.pwd() != "/" + vita_dir.replace("ux0:", "ux0:/", 1):
            raise ValueError("FTP current directory does not match the fixed inbox path")
        state = "uploading .part"
        ftp.storbinary("STOR vita_devloop.vpk.part", io.BytesIO(data), blocksize=64 * 1024)
        state = "verifying .part"
        verify_remote(ftp, "vita_devloop.vpk.part", package)
        state = "renaming verified .part; final outcome may be uncertain"
        ftp.rename("vita_devloop.vpk.part", "vita_devloop.vpk")
        state = "verifying final VPK"
        observed = verify_remote(ftp, "vita_devloop.vpk", package)
        receipt = {
            "verified_utc": datetime.now(timezone.utc).isoformat(), "transport": "FTP",
            "endpoint": f"{config['host']}:{config['port']}", **package,
            "observed_sha256": observed, "vita_path": vita_dir + "/vita_devloop.vpk",
            "read_back_checks": 2, "installation": "pending", "attempt": attempt,
        }
        # A lost QUIT response cannot undo a completed transfer and two verified reads.
        try:
            ftp.quit()
        except ftplib.all_errors:
            pass
        return receipt
    except (OSError, EOFError, ftplib.Error, ValueError) as error:
        raise RuntimeError(
            f"FTP staging failed while {state}. Attempt: {vita_dir}. "
            "No automatic retry or cleanup was performed; any .part or final VPK may remain. "
            f"Cause: {type(error).__name__}."
        ) from error
    finally:
        ftp.close()
