"""Serve Maker Constellation and refresh its catalog on a fixed interval."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

from update_catalog import build_catalog, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_PATH = PROJECT_ROOT / "data" / "projects.json"
SOURCES_PATH = PROJECT_ROOT / "data" / "sources.json"


def refresh_catalog() -> None:
    projects, sources = build_catalog()
    write_json(PROJECTS_PATH, projects)
    write_json(SOURCES_PATH, sources)
    print(f"Catalog updated: {len(projects)} projects from {len(sources)} repositories")


def update_loop(interval_seconds: float, stop_event: Event) -> None:
    while not stop_event.wait(interval_seconds):
        try:
            refresh_catalog()
        except Exception as error:  # Keep serving the last valid catalog.
            print(f"Catalog update failed: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve and automatically update Maker Constellation")
    parser.add_argument("--port", type=int, default=4173, help="HTTP server port")
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=6,
        help="hours between catalog refreshes",
    )
    parser.add_argument(
        "--skip-initial-update",
        action="store_true",
        help="serve existing data before the first scheduled refresh",
    )
    args = parser.parse_args()

    if args.interval_hours <= 0:
        parser.error("--interval-hours must be greater than zero")

    if not args.skip_initial_update:
        try:
            refresh_catalog()
        except Exception as error:
            print(f"Initial catalog update failed; serving existing data: {error}")

    stop_event = Event()
    updater = Thread(
        target=update_loop,
        args=(args.interval_hours * 60 * 60, stop_event),
        daemon=True,
    )
    updater.start()

    handler = partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
    server = ThreadingHTTPServer(("", args.port), handler)
    print(
        f"Serving Maker Constellation at http://localhost:{args.port} "
        f"(updates every {args.interval_hours:g} hours)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
