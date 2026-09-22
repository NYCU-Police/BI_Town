#!/usr/bin/env python3
"""Serve the Godot web export with COOP/COEP headers.

Godot 4 WASM can require cross-origin isolation (SharedArrayBuffer).
`python -m http.server` does not send these headers.
"""

from __future__ import annotations

import argparse
import logging
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOGGER = logging.getLogger("serve_web")

DEFAULT_PORT = 8080
WEB_ROOT = Path(__file__).resolve().parent / "build" / "web"


class CoopCoepHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".wasm": "application/wasm",
        ".pck": "application/octet-stream",
    }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Serve BI_Town Godot web export")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    index = WEB_ROOT / "index.html"
    if not index.is_file():
        raise SystemExit(
            f"Missing {index}. Export the Web preset first "
            "(Project → Export → Web, or godot --export-release Web)."
        )

    server = ThreadingHTTPServer(("127.0.0.1", args.port), CoopCoepHandler)
    LOGGER.info("Serving %s at http://127.0.0.1:%s/", WEB_ROOT, args.port)
    LOGGER.info("COOP/COEP enabled. Backend should already be on :8000.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
