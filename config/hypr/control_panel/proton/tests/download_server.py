"""Real libcurl regression tests against a fault-injecting, locally trusted HTTPS server."""
import collections
import http.server
import pathlib
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # A cancelled client intentionally closes its connection.


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls = collections.Counter()
    ranges = collections.defaultdict(list)

    def log_message(self, *args):
        pass

    def respond(self, status, body, headers=None, cut=False, slow=False):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if cut:
            self.wfile.write(body[:65536])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            self.close_connection = True
        elif slow:
            for pos in range(0, len(body), 8192):
                self.wfile.write(body[pos:pos + 8192])
                self.wfile.flush()
                time.sleep(0.015)
        else:
            self.wfile.write(body)

    def do_GET(self):
        name = self.path.strip("/")
        self.calls[name] += 1
        count = self.calls[name]
        self.ranges[name].append(self.headers.get("Range", ""))
        if name == "metadata":
            self.respond(503 if count == 1 else 200, b"busy" if count == 1 else b"recovered")
            return
        if name == "missing":
            self.respond(404, b"missing")
            return
        body = b"a" * (256 * 1024)
        if name.startswith("changed") and count > 1:
            body = b"b" * len(body)
        headers = {"ETag": '"new"' if name.startswith("changed") and count > 1 else '"original"'}
        if count == 1 and name not in ("cancel", "crash"):
            self.respond(200, body, headers, cut=True)
            return
        requested = self.headers.get("Range")
        if requested and name not in ("ignore", "changed"):
            offset = int(requested.removeprefix("bytes=").removesuffix("-"))
            if name == "range416" and count == 2:
                self.respond(416, b"", {"Content-Range": f"bytes */{len(body)}"})
                return
            first = offset + 1 if name == "invalid-range" else offset
            headers["Content-Range"] = f"bytes {first}-{len(body) - 1}/{len(body)}"
            assert self.headers.get("If-Range") == '"original"'
            self.respond(206, body[offset:], headers)
        else:
            self.respond(200, body, headers, slow=name in ("cancel", "crash"))


with tempfile.TemporaryDirectory(prefix="xetalproton-https-") as folder:
    root = pathlib.Path(folder)
    cert, key = root / "cert.pem", root / "key.pem"
    subprocess.run([
        sys.argv[2], "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server = Server(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run([
            sys.argv[1], "--download-tests", f"https://127.0.0.1:{server.server_port}", str(cert),
        ], check=True, timeout=90)
        for name in ("resume", "ignore", "changed", "unknown", "cancel", "crash"):
            assert Handler.calls[name] == 2, (name, Handler.calls)
            assert Handler.ranges[name][1].startswith("bytes="), Handler.ranges
        assert Handler.calls["range416"] == 3 and Handler.ranges["range416"][-1] == ""
        assert Handler.calls["changed-range"] == 3 and Handler.ranges["changed-range"][-1] == ""
        assert Handler.calls["missing"] == 1
        assert Handler.calls["metadata"] == 2
        print("Server verified Range, If-Range, cache reuse and bounded retry behavior.")
    finally:
        server.shutdown()
        server.server_close()
