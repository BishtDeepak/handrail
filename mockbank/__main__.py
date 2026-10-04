"""Run MockBank: ``python -m mockbank [--port 8765]``."""

from __future__ import annotations

import argparse

import uvicorn

from mockbank.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MockBank target app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"MockBank on http://{args.host}:{args.port}/  (faults: /__mockbank/)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
