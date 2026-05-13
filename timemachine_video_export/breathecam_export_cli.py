"""Export raw RGB frames from a Breathecam thumbnail URL.

Output protocol on stdout:
  1. One ASCII-only JSON line (terminated by \\n) describing the thumbnail,
     the TimeMachine, and the exact frames being emitted.
  2. Raw 8-bit R,G,B pixel bytes: nframes * height * width * 3 bytes,
     frame-major, row-major top-to-bottom, no padding.
  3. One ASCII-only JSON line (terminated by \\n) with per-stage timing stats.

With --pixels-output PATH the binary frames go to that file and the two JSON
lines (header + trailing stats) remain on stdout. Useful when you want to
read the JSON without piping gigabytes through stdout.

Informational logging goes to stderr so the binary stdout stream is clean.

Python consumer:
    line = sys.stdin.buffer.readline()
    meta = json.loads(line)
    r = meta['render']
    pixels = sys.stdin.buffer.read(r['total_pixel_bytes'])
    frames = np.frombuffer(pixels, dtype=np.uint8).reshape(
        r['nframes'], r['output_height'], r['output_width'], 3)
    stats_line = sys.stdin.buffer.readline()
    stats = json.loads(stats_line)

Ruby 2.7 consumer:
    require 'json'
    STDIN.binmode
    meta   = JSON.parse(STDIN.gets)        # ASCII-only header line
    r      = meta['render']
    bytes_per_frame = r['output_width'] * r['output_height'] * 3
    r['nframes'].times do |i|
      frame = STDIN.read(bytes_per_frame)  # binary string, R,G,B,R,G,B,...
      # ... process frame ...
    end
    stats = JSON.parse(STDIN.gets)         # trailing stats line
"""
import argparse
import json
import sys

from .thumbnail_api import BreathecamThumbnail
from .timemachine import TimeMachine
from .video_renderer import OutputToStream, render_video


def _parse_size(s: str):
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected WIDTHxHEIGHT, got {s!r}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Non-integer size {s!r}")
    if w % 2 or h % 2:
        raise argparse.ArgumentTypeError(f"Both dimensions must be even, got {s!r}")
    return w, h


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="breathecam-thumbnail-export",
        description=(
            "Export raw RGB frames from a Breathecam thumbnail URL. "
            "Begin/end times come from bt/et in the URL itself."
        ),
        epilog=(
            "Output: one ASCII JSON line + '\\n', then raw uint8 R,G,B pixels "
            "(nframes * height * width * 3 bytes). Logging goes to stderr."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url",
                        help="Breathecam thumbnail URL (e.g. https://breathecam.org#...)")
    parser.add_argument("-o", "--output", default="-",
                        help="Output path, or '-' for stdout (default: -).")
    parser.add_argument("--size", type=_parse_size, default=None,
                        metavar="WxH",
                        help="Output size in pixels (both even). "
                             "Default: v-rect dimensions rounded down to even.")
    parser.add_argument("--pixels-output", default=None, metavar="PATH",
                        help="Debug: write the binary RGB frames to PATH and keep "
                             "the header + trailing stats JSON lines on stdout. "
                             "Use /dev/null to discard the pixels entirely.")
    args = parser.parse_args(argv)

    # Capture binary stdout NOW and redirect text-mode stdout to stderr before
    # any code can print() to the original stdout (e.g., TimeMachine.__init__
    # logs "Fetching tm.json"). Otherwise those prints would corrupt the
    # protocol on stdout. We need this whenever ANY JSON or pixel data is
    # destined for stdout — i.e., for both -o - and --pixels-output PATH.
    raw_stdout = sys.stdout.buffer
    sys.stdout = sys.stderr

    thumbnail = BreathecamThumbnail(args.url)
    begin = thumbnail.begin_time_in_camera_timezone()
    end = thumbnail.end_time_in_camera_timezone()
    tm_url = thumbnail.timemachine_root_url()
    source_rect = thumbnail.view_rect()

    if args.size is None:
        # thumbnail.width / .height were already even-rounded from the v-rect
        # by Thumbnail.__init__ for the bare-URL form.
        out_w, out_h = thumbnail.width, thumbnail.height
    else:
        out_w, out_h = args.size

    tm = TimeMachine(tm_url)
    start_frame = tm.frameno_from_date_after_or_equal(begin)
    end_frame = tm.frameno_from_date_before_or_equal(end)
    nframes = end_frame - start_frame + 1
    if nframes <= 0:
        parser.error(
            f"No frames in range: bt={thumbnail.bt}, et={thumbnail.et} "
            f"yields start_frame={start_frame}, end_frame={end_frame}"
        )

    bytes_per_frame = out_w * out_h * 3
    metadata = {
        "thumbnail": {
            "url": args.url,
            "s": thumbnail.s,
            "d": thumbnail.d,
            "v": [source_rect.x1, source_rect.y1, source_rect.x2, source_rect.y2],
            "bt": thumbnail.bt,
            "et": thumbnail.et,
            "fps": thumbnail.fps,
            "begin_time": begin.isoformat(),
            "end_time": end.isoformat(),
            "timemachine_root_url": tm_url,
        },
        "timemachine": {
            "root_url": tm.root_url,
            "tile_root_url": tm.tile_root_url,
            "fps": tm.fps(),
            "width": tm.width(),
            "height": tm.height(),
            "tile_width": tm.tile_width(),
            "tile_height": tm.tile_height(),
            "nlevels": tm.r["nlevels"],
            "level_info": tm.level_info(),
            "capture_times": tm.capture_times(),
        },
        "render": {
            "output_width": out_w,
            "output_height": out_h,
            "source_rect": [source_rect.x1, source_rect.y1, source_rect.x2, source_rect.y2],
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frame_indices": list(range(start_frame, end_frame + 1)),
            "nframes": nframes,
            "bytes_per_frame": bytes_per_frame,
            "total_pixel_bytes": nframes * bytes_per_frame,
        },
    }

    # ensure_ascii=True is the json.dumps default, but pin it explicitly: the
    # consumer reads the header line as bytes and assumes ASCII-only content.
    header = json.dumps(metadata, ensure_ascii=True).encode("ascii") + b"\n"

    # Decide where header JSON, pixel frames, and trailing stats JSON each go.
    if args.pixels_output is not None:
        # Debug split: JSON to stdout, pixels to a separate file.
        json_stream = raw_stdout
        pixel_stream = open(args.pixels_output, "wb")
        close_pixel_stream = True
    elif args.output == "-":
        json_stream = raw_stdout
        pixel_stream = raw_stdout
        close_pixel_stream = False
    else:
        pixel_stream = open(args.output, "wb")
        json_stream = pixel_stream  # all three sections concatenated into one file
        close_pixel_stream = True

    try:
        json_stream.write(header)
        json_stream.flush()
        result = render_video(
            timemachine_root_url=tm_url,
            begin_datetime=begin,
            end_datetime=end,
            source_rect=source_rect,
            output=OutputToStream(pixel_stream, out_w, out_h),
        )
        if pixel_stream is not json_stream:
            pixel_stream.flush()
        trailer = json.dumps({"stats": result["stats"]}, ensure_ascii=True).encode("ascii") + b"\n"
        json_stream.write(trailer)
        json_stream.flush()
    finally:
        if close_pixel_stream:
            pixel_stream.close()


if __name__ == "__main__":
    main()
