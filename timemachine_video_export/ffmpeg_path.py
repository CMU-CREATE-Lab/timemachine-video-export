import os
import shutil
import sys


def resolve_ffmpeg_tool(name):
    """Return a path to 'ffmpeg' or 'ffprobe'.

    If FFMPEG_DIR is set, look for the tool in that directory. Otherwise
    fall back to PATH.

    Prints guidance to stderr and raises RuntimeError if not found.
    """
    assert name in ("ffmpeg", "ffprobe"), name

    override = os.environ.get("FFMPEG_DIR")
    if override:
        candidate = os.path.join(override, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        _report_missing(name, override)

    found = shutil.which(name)
    if found:
        return found
    _report_missing(name, None)


def _report_missing(name, override):
    if override:
        print(
            f"\nERROR: FFMPEG_DIR is set to {override!r}\n"
            f"but '{name}' was not found there.\n"
            f"FFMPEG_DIR must be a directory containing both ffmpeg and ffprobe.\n",
            file=sys.stderr,
        )
    else:
        print(
            f"\nERROR: '{name}' not found on PATH.\n"
            f"Either install ffmpeg on your PATH, or set FFMPEG_DIR to the\n"
            f"directory containing ffmpeg and ffprobe, e.g.:\n"
            f"    export FFMPEG_DIR=/usr/local/bin\n",
            file=sys.stderr,
        )
    raise RuntimeError(f"{name} not found (set FFMPEG_DIR; see stderr for details)")
