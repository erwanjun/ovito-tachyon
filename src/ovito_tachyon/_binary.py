"""Locate and run the Tachyon executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

_EXE = "tachyon.exe" if sys.platform == "win32" else "tachyon"


class TachyonNotFoundError(RuntimeError):
    pass


def find_tachyon() -> str:
    """Return the path of the Tachyon executable.

    Search order: ``$OVITO_TACHYON_EXE``, the copy bundled with this package,
    then ``tachyon`` on ``PATH``.
    """
    env = os.environ.get("OVITO_TACHYON_EXE")
    if env:
        if not Path(env).is_file():
            raise TachyonNotFoundError(f"OVITO_TACHYON_EXE points to a missing file: {env}")
        return env
    bundled = Path(__file__).resolve().parent / "bin" / _EXE
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("tachyon")
    if found:
        return found
    raise TachyonNotFoundError(
        "Tachyon executable not found. Reinstall ovito-tachyon from a wheel, "
        "or set OVITO_TACHYON_EXE to a tachyon binary."
    )


def run_tachyon(scene_file, output_file, threads: Optional[int] = None, verbose: bool = False) -> None:
    cmd = [find_tachyon(), str(scene_file), "-format", "PPM", "-o", str(output_file)]
    if threads:
        cmd += ["-numthreads", str(int(threads))]
    # Keep GUI apps on Windows from flashing a console window for every frame.
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    if verbose:
        print(proc.stdout)
    if proc.returncode != 0 or not Path(output_file).is_file():
        raise RuntimeError(f"Tachyon failed (exit code {proc.returncode}):\n{proc.stdout}")
    # Tachyon reports parse errors on stdout but still exits 0.
    for line in proc.stdout.splitlines():
        if "Parse Error" in line or "Undefined texture" in line:
            raise RuntimeError(f"Tachyon could not parse the scene:\n{proc.stdout}")
