"""Make the desktop engine importable on a machine whose bundled ExifTool is dead.

The repo ships `exiftool_bin` as a bare Perl script. On a machine whose Perl
can't load `Image::ExifTool` — the exact failure this web port exists to
sidestep — `pyexiftool`'s `-stay_open` handshake hangs forever, so every
reference-generation run stalls with no output.

Importing this module (before `core.thermal_engine` is used) swaps in a system
`exiftool` when the bundled one can't even print its version. It only touches the
ground-truth generators; the parser under test never shells out.
"""
import os
import shutil
import subprocess

import core.thermal_engine as _engine_mod

_orig_resource_path = _engine_mod.resource_path


def _bundled_exiftool_works(path: str) -> bool:
    if not (path and os.access(path, os.X_OK)):
        return False
    try:
        return subprocess.run([path, "-ver"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _resource_path(rel):
    if rel == "exiftool_bin":
        bundled = _orig_resource_path(rel)
        if not _bundled_exiftool_works(bundled):
            system = shutil.which("exiftool")
            if system:
                return system
    return _orig_resource_path(rel)


_engine_mod.resource_path = _resource_path
