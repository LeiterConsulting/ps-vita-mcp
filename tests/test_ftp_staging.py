"""Exercise upload, verification and faults through actual MCP stdio."""
import asyncio
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ftp_fixture import Fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
from ftp_staging import endpoint, stage_package, validate_package


def content(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


def must_fail(function, *args):
    try:
        function(*args)
    except (ValueError, RuntimeError):
        return
    raise AssertionError("Invalid input was accepted")


async def main():
    package_path = ROOT / "dist/devloop/vita_devloop.vpk"
    report_path = ROOT / "dist/devloop/build-report.json"
    report = json.loads(report_path.read_text())
    expected = report["package"]["sha256"]
    package_data, metadata = validate_package(package_path, report_path, expected)
    fixture = Fixture()
    try:
        with tempfile.TemporaryDirectory(prefix="vita-ftp-test-") as folder:
            temporary = Path(folder)
            config = temporary / "ftp.json"
            config.write_text(json.dumps({"host": "127.0.0.1", "port": fixture.port}))
            for host, port in (("8.8.8.8", 1337), ("0.0.0.0", 1337), ("224.0.0.1", 1337), ("127.0.0.1", 0), ("127.0.0.1", "1337")):
                bad_config = temporary / "bad-config.json"
                bad_config.write_text(json.dumps({"host": host, "port": port}))
                must_fail(endpoint, bad_config)
            bad_config.write_text(json.dumps({"host": "127.0.0.1", "port": fixture.port, "username": "bad\r\nUSER root"}))
            must_fail(endpoint, bad_config)
            must_fail(validate_package, package_path, report_path, "0" * 64)
            must_fail(validate_package, package_path, report_path, "../bad")
            bad_report = temporary / "report.json"
            bad_version="99.99" if report["package"]["version"]!="99.99" else "00.00"
            for field, value in (("version", bad_version), ("titleId", "OTHER0000"), ("bytes", 1)):
                changed = json.loads(report_path.read_text()); changed["package"][field] = value
                bad_report.write_text(json.dumps(changed))
                must_fail(validate_package, package_path, bad_report, expected)
            # Even a self-consistent hash/report cannot authorize a different title ID.
            changed_package = temporary / "vita_devloop.vpk"
            with zipfile.ZipFile(io.BytesIO(package_data)) as original, zipfile.ZipFile(changed_package, "w") as changed:
                for name in original.namelist():
                    data = original.read(name)
                    if name == "sce_sys/param.sfo": data = data.replace(b"CHRS00003", b"OTHER0000")
                    changed.writestr(name, data)
            bad_hash = hashlib.sha256(changed_package.read_bytes()).hexdigest()
            changed = json.loads(report_path.read_text()); changed["package"].update(sha256=bad_hash, bytes=changed_package.stat().st_size)
            bad_report.write_text(json.dumps(changed))
            must_fail(validate_package, changed_package, bad_report, bad_hash)
            assert not fixture.commands
            print("PASS local endpoint/credentials, hash, size, version and SFO rejection before any FTP writes")

            parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "bridge/server.py")],
                                              env={**os.environ, "VITA_DEVLOOP_FTP_CONFIG": str(config)})
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    tool = next(tool for tool in tools if tool.name == "vita_stage_package")
                    assert tool.annotations.readOnlyHint is False and tool.annotations.idempotentHint is False
                    assert set(tool.inputSchema["properties"]) == {"expected_sha256"}
                    first = content(await session.call_tool("vita_stage_package", {"expected_sha256": expected}))
                    remote = "/" + first["vita_path"].replace("ux0:", "ux0:/", 1)
                    assert fixture.files[remote] == package_data
                    assert first["sha256"] == first["observed_sha256"] == expected and first["installation"] == "pending"
                    assert first["read_back_checks"] == 2 and first["bytes"] == len(package_data)
                    assert not any(path.endswith(".part") for path in fixture.files)
                    second = content(await session.call_tool("vita_stage_package", {"expected_sha256": expected}))
                    assert first["vita_path"] != second["vita_path"] and fixture.files[remote] == package_data
                    assert not any(command == "NLST" for command, _ in fixture.commands)
                    print("PASS real MCP schema and binary FTP upload, two read-backs, rename, unique paths and preservation")
                    before = len(fixture.commands)
                    assert (await session.call_tool("vita_stage_package", {"expected_sha256": "0" * 64})).isError
                    assert len(fixture.commands) == before
                    print("PASS MCP wrong-hash call never connects to FTP")
                    for fault, expected_stage in (
                        ("corrupt_part", "verifying .part"), ("truncate_upload", "verifying .part"),
                        ("drop_upload", "uploading .part"), ("oversize_read", "verifying .part"),
                        ("unsupported_rename", "renaming verified .part"), ("drop_rename", "final outcome may be uncertain"),
                        ("corrupt_final", "verifying final VPK"), ("collision", "creating fresh attempt directory"),
                    ):
                        fixture.fault = fault
                        commands_before = len(fixture.commands)
                        files_before = set(fixture.files)
                        result = await session.call_tool("vita_stage_package", {"expected_sha256": expected})
                        assert result.isError and expected_stage in result.content[0].text, result
                        new_commands = fixture.commands[commands_before:]
                        assert sum(command == "STOR" for command, _ in new_commands) == (0 if fault == "collision" else 1)
                        assert not any(command in ("DELE", "RMD") for command, _ in new_commands)
                        additions = set(fixture.files) - files_before
                        if fault in ("drop_rename", "corrupt_final"):
                            assert len(additions) == 1 and next(iter(additions)).endswith(".vpk")
                        elif fault != "collision":
                            assert len(additions) == 1 and next(iter(additions)).endswith(".part")
                        assert fixture.files[remote] == package_data
                        print(f"PASS {fault}: honest error, no retry/cleanup/overwrite")
                    fixture.fault = None
            # Force a true UUID collision; the existing successful file remains intact.
            with patch("ftp_staging.uuid.uuid4") as random_id:
                random_id.return_value.hex = first["attempt"].rsplit("-", 1)[1]
                must_fail(stage_package, package_path, report_path, config, expected)
            assert fixture.files[remote] == package_data
            print("PASS forced existing-directory collision preserves its package")
            fixture.close()
            must_fail(stage_package, package_path, report_path, config, expected)
            print("PASS offline FTP error leaves installation pending")
    finally:
        if fixture.thread.is_alive(): fixture.close()
    print("13 FTP staging test groups passed against a simulated FTP device through real MCP stdio.")


if __name__ == "__main__": asyncio.run(main())
