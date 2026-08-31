# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bound the test server lifetime independently of the official SDK's process group.

This is verification scaffolding for trusted examples and controlled fixtures,
not a production server launcher or graceful-shutdown mechanism.
"""

from __future__ import annotations

import math
import os
import runpy
import sys
import threading
from pathlib import Path


def run_server(example: Path, *, timeout: float = 55) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("test server lifetime must be finite and positive")
    # The SDK may create a separate POSIX session or Windows Job Object. If
    # client cleanup fails, this server must still exit without a parent signal.
    watchdog = threading.Timer(timeout, os._exit, args=(124,))
    watchdog.daemon = True
    watchdog.start()
    try:
        runpy.run_path(str(example.resolve(strict=True)), run_name="__main__")
    finally:
        watchdog.cancel()
        watchdog.join(timeout=1)


if __name__ == "__main__":
    run_server(Path(sys.argv[1]))
