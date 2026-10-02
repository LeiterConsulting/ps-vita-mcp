"""Isolated in-memory FTP server with deliberate transport and data faults."""
import posixpath
import socket
import socketserver
import threading


class Fixture:
    def __init__(self):
        self.files = {}
        self.directories = {"/", "/ux0:", "/ux0:/data"}
        self.commands = []
        self.fault = None
        self.lock = threading.Lock()
        fixture = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.cwd = "/"
                self.passive = None
                self.rename_from = None
                self.reply("220 SIMULATED FTP DEVICE - TEST ONLY")
                try:
                    while line := self.rfile.readline(4096):
                        command, _, argument = line.decode().rstrip("\r\n").partition(" ")
                        with fixture.lock:
                            fixture.commands.append((command, argument))
                        if command == "QUIT":
                            self.reply("221 Goodbye"); break
                        if command == "USER": self.reply("331 Password required")
                        elif command == "PASS": self.reply("230 Logged in")
                        elif command == "TYPE": self.reply("200 Binary type set")
                        elif command == "PWD": self.reply(f'257 "{self.cwd}"')
                        elif command == "CWD":
                            path = self.path(argument)
                            if path in fixture.directories:
                                self.cwd = path; self.reply("250 Directory changed")
                            else: self.reply("550 Directory does not exist")
                        elif command == "MKD":
                            path = self.path(argument)
                            if (path in fixture.directories or posixpath.dirname(path) not in fixture.directories
                                    or (fixture.fault == "collision" and self.cwd.endswith("/inbox"))):
                                self.reply("550 Directory already exists or parent unavailable")
                            else:
                                fixture.directories.add(path); self.reply(f'257 "{path}" created')
                        elif command == "PASV":
                            self.passive = socket.socket()
                            self.passive.bind(("127.0.0.1", 0)); self.passive.listen(1); self.passive.settimeout(5)
                            port = self.passive.getsockname()[1]
                            # Deliberately advertise a different IPv4; the client must pin the data host.
                            self.reply(f"227 Entering Passive Mode (203,0,113,77,{port // 256},{port % 256})")
                        elif command in ("STOR", "RETR"):
                            path = self.path(argument)
                            if command == "RETR" and path not in fixture.files:
                                self.reply("550 File unavailable"); continue
                            self.reply("150 Data connection opening")
                            connection, _ = self.passive.accept()
                            connection.settimeout(5)
                            with connection:
                                if command == "STOR":
                                    parts = []
                                    while block := connection.recv(65536): parts.append(block)
                                    data = b"".join(parts)
                                    if fixture.fault in ("truncate_upload", "drop_upload"): data = data[:17]
                                    fixture.files[path] = data
                                else:
                                    data = fixture.files[path]
                                    if ((fixture.fault == "corrupt_part" and path.endswith(".part"))
                                            or (fixture.fault == "corrupt_final" and path.endswith(".vpk"))):
                                        data = bytes([data[0] ^ 1]) + data[1:]
                                    if fixture.fault == "oversize_read": data += b"extra"
                                    connection.sendall(data)
                            self.passive.close(); self.passive = None
                            if command == "STOR" and fixture.fault == "drop_upload": break
                            self.reply("226 Transfer complete")
                        elif command == "RNFR":
                            self.rename_from = self.path(argument)
                            self.reply("350 Ready for destination")
                        elif command == "RNTO":
                            if fixture.fault == "unsupported_rename":
                                self.reply("502 Rename unsupported"); continue
                            target = self.path(argument)
                            if target in fixture.files:
                                self.reply("550 Refusing overwrite"); continue
                            fixture.files[target] = fixture.files.pop(self.rename_from)
                            if fixture.fault == "drop_rename": break
                            self.reply("250 Rename complete")
                        else: self.reply("502 Command unsupported")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    if self.passive is not None: self.passive.close()

            def reply(self, message):
                self.wfile.write((message + "\r\n").encode()); self.wfile.flush()

            def path(self, argument):
                return posixpath.normpath("/" + argument if argument.startswith("ux0:")
                                          else argument if argument.startswith("/")
                                          else self.cwd + "/" + argument)

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self): return self.server.server_address[1]

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
