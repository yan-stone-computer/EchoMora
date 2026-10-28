from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from .engine import EchoMora
from .server import serve
from .settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the EchoMora local demo")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--open", action="store_true", help="open the demo in a browser")
    args = parser.parse_args()

    settings = Settings.load(Path.cwd())
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    if args.db:
        settings.db_path = args.db.resolve()

    engine = EchoMora(settings)
    if args.open:
        webbrowser.open(f"http://{settings.host}:{settings.port}")
    serve(engine, settings.host, settings.port)


if __name__ == "__main__":
    main()

