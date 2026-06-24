#!/usr/bin/env python3
"""Convenience runner — `python run.py` starts the engine.

This is a thin CLI wrapper around :func:`main.main`, which contains the
actual FastAPI + uvicorn startup logic. The two entry points are
intentionally split:

* ``main.py``  — application factory (``create_app``) + ``main()`` startup.
* ``run.py``   — argparse CLI that maps flags to ``HERMES_*`` env vars and
                 delegates to ``main.main()``.

Either ``python run.py`` or ``python main.py`` starts the server; the
Makefile uses ``run.py`` for its ``--debug`` convenience flag.

Usage:
    python run.py                  # production (127.0.0.1:8080)
    python run.py --debug          # debug mode with verbose logging
    python run.py --host 0.0.0.0   # listen on all interfaces
    python run.py --port 9090      # custom port
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure the project root is on sys.path so `from config` etc. resolve
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Engine")
    parser.add_argument("--host", default=None, help="Bind address")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Override env from CLI args
    if args.host:
        os.environ.setdefault("HERMES_HOST", args.host)
    if args.port:
        os.environ.setdefault("HERMES_PORT", str(args.port))
    if args.debug:
        os.environ.setdefault("HERMES_DEBUG", "true")

    from main import main as engine_main
    engine_main()


if __name__ == "__main__":
    main()
