"""Serve a runner-local module bundle only for the duration of overlay tests."""

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
from threading import Thread


@contextmanager
def serve_overlay_modules():
    archive_name = os.environ.get("ADIDT_OVERLAY_MODULES_ARCHIVE")
    if not archive_name:
        yield
        return
    if os.environ.get("ADIDT_OVERLAY_MODULES_URL") or os.environ.get(
        "ADIDT_OVERLAY_MODULES_SHA256"
    ):
        raise ValueError("Select either a local overlay module archive or URL/checksum")
    archive = Path(archive_name)
    if not archive.is_file():
        raise ValueError(
            f"Overlay module archive is not a runner-local file: {archive}"
        )
    host = os.environ.get("ADIDT_OVERLAY_MODULES_HOST")
    if not host:
        raise ValueError(
            "Set ADIDT_OVERLAY_MODULES_HOST to the runner's board-reachable IPv4 address"
        )
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/modules.tar.gz":
                self.send_error(404)
                return
            with archive.open("rb") as source:
                self.send_response(200)
                self.send_header(
                    "Content-Length", str(os.fstat(source.fileno()).st_size)
                )
                self.end_headers()
                shutil.copyfileobj(source, self.wfile)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["ADIDT_OVERLAY_MODULES_URL"] = (
        f"http://{host}:{server.server_port}/modules.tar.gz"
    )
    os.environ["ADIDT_OVERLAY_MODULES_SHA256"] = digest.hexdigest()
    try:
        yield
    finally:
        os.environ.pop("ADIDT_OVERLAY_MODULES_URL", None)
        os.environ.pop("ADIDT_OVERLAY_MODULES_SHA256", None)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
