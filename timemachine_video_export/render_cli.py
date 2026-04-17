"""Command-line tool: render a video from a TimeMachine source."""
import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .rectangle import Rectangle
from .video_renderer import OutputToVideo, render_video


def _parse_datetime(s: str, default_tz):
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Cannot parse datetime {s!r}: {e}")
    if dt.tzinfo is None:
        if default_tz is None:
            raise argparse.ArgumentTypeError(
                f"Datetime {s!r} has no timezone; pass --timezone, "
                f"or use an ISO string with offset like 2025-02-15T08:00:00-05:00"
            )
        dt = dt.replace(tzinfo=default_tz)
    return dt


def _parse_rect(s: str) -> Rectangle:
    parts = s.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"Expected X1,Y1,X2,Y2, got {s!r}")
    try:
        x1, y1, x2, y2 = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Non-numeric value in rect {s!r}")
    return Rectangle(x1, y1, x2, y2)


def _parse_size(s: str):
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected WIDTHxHEIGHT, got {s!r}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Non-integer size {s!r}")
    return w, h


def _parse_timezone(s: str) -> ZoneInfo:
    try:
        return ZoneInfo(s)
    except ZoneInfoNotFoundError:
        raise argparse.ArgumentTypeError(f"Unknown timezone {s!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="timemachine-render",
        description="Render an MP4 from a TimeMachine source.",
        epilog=(
            "Example:\n"
            "  timemachine-render \\\n"
            "    --url https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2025-02-15.timemachine \\\n"
            "    --begin '2025-02-15 08:00:00' --end '2025-02-15 08:01:00' \\\n"
            "    --timezone America/New_York \\\n"
            "    --source-rect 0,0,6613,2717 --size 3840x2160 \\\n"
            "    --output clairton.mp4"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True,
                        help="TimeMachine root URL (no trailing slash)")
    parser.add_argument("--begin", required=True,
                        help="Begin datetime (ISO 8601). Needs --timezone if naive.")
    parser.add_argument("--end", required=True,
                        help="End datetime (ISO 8601). Needs --timezone if naive.")
    parser.add_argument("--timezone", type=_parse_timezone, default=None,
                        help="Timezone name (e.g. America/New_York) for naive datetimes.")
    parser.add_argument("--source-rect", required=True, type=_parse_rect,
                        metavar="X1,Y1,X2,Y2",
                        help="Source rectangle in TimeMachine pixel coordinates.")
    parser.add_argument("--size", required=True, type=_parse_size,
                        metavar="WxH",
                        help="Output size in pixels. Both dimensions must be even.")
    parser.add_argument("--output", required=True,
                        help="Output MP4 path.")
    args = parser.parse_args(argv)

    try:
        begin = _parse_datetime(args.begin, args.timezone)
        end = _parse_datetime(args.end, args.timezone)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    width, height = args.size
    output = OutputToVideo(args.output, width, height)
    render_video(
        timemachine_root_url=args.url,
        begin_datetime=begin,
        end_datetime=end,
        source_rect=args.source_rect,
        output=output,
    )


if __name__ == "__main__":
    main()
