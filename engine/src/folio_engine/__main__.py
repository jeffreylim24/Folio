import argparse
import asyncio
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .server import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="folio-engine")
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    token = os.environ.get("FOLIO_ENGINE_TOKEN")
    if not token:
        print("FOLIO_ENGINE_TOKEN is not set", file=sys.stderr)
        return 2

    args.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(token, args.data_dir)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    print(f"FOLIO_ENGINE_READY port={port}", flush=True)

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    asyncio.run(server.serve(sockets=[sock]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
