# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Install exactly one wheel offline in a temporary venv and verify its real journeys."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def verify(wheel: Path) -> None:
    """Never import the source package or use the invoking environment's dependencies."""

    wheel = wheel.resolve(strict=True)
    if wheel.suffix != ".whl":
        raise ValueError("expected a .whl distribution")
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="samsarix-wheel-") as temporary:
        workspace = Path(temporary)
        environment = workspace / "venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [sys.executable, "-I", "-m", "venv", str(environment)], check=True, timeout=120
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=workspace,
            check=True,
            timeout=120,
        )
        subprocess.run(
            [str(python), "-I", "-m", "pip", "check"], cwd=workspace, check=True, timeout=30
        )
        for script in ("smoke_check.py", "mcp_smoke_check.py"):
            subprocess.run(
                [str(python), "-I", str(scripts / script)], cwd=workspace, check=True, timeout=45
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "wheel", type=Path, nargs="?", help="exact wheel path; defaults to the sole dist/*.whl"
    )
    arguments = parser.parse_args()
    wheel = arguments.wheel
    if wheel is None:
        candidates = list(Path("dist").glob("*.whl"))
        if len(candidates) != 1:
            parser.error("dist/ must contain exactly one wheel; pass an explicit artifact path")
        wheel = candidates[0]
    verify(wheel)


if __name__ == "__main__":
    main()
