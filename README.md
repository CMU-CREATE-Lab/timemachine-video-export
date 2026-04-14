# TimeMachine Video Export

A Python library for exporting videos from Breathecam timelapse cameras.

## Installation

```bash
pip install -e .
```

Or install with test dependencies:

```bash
pip install -e ".[test]"
```

## Usage

### Download frames at any scale

Use `download_scaled_video_frame_range` to extract a region of the timelapse at any resolution. The source rectangle is in full-resolution coordinates and can have non-integer bounds. The method picks a tile level with more detail than requested and uses Lanczos interpolation to resize to the exact output dimensions.

```python
from timemachine_video_export import TimeMachine, Rectangle

tm = TimeMachine("https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2024-10-23.timemachine")

# Download a region at 10% scale with sub-pixel offset
frames = tm.download_scaled_video_frame_range(
    start_frame_no=0,
    nframes=15,
    source_rect=Rectangle(x1=0.5, y1=0.25, x2=6613.5, y2=2717.25),
    output_width=660,
    output_height=270
)
```

### Download frames at native tile resolution

For pixel-exact downloads without interpolation, use `download_video_frame_range` with an integer rectangle and a power-of-2 subsample factor:

```python
from timemachine_video_export import TimeMachine, Rectangle

tm = TimeMachine("https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2024-10-23.timemachine")

frames = tm.download_video_frame_range(
    start_frame_no=0,
    nframes=15,
    rect=Rectangle(x1=0, y1=0, x2=1920, y2=1080),
    subsample=1
)
```

### Render video from a Breathecam thumbnail

The `video_renderer` module provides higher-level functions for rendering complete videos to MP4:

```python
from timemachine_video_export.video_renderer import render_video_site
from datetime import datetime
from zoneinfo import ZoneInfo

begin = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
end = datetime(2025, 2, 15, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))

render_video_site("Clairton", begin, end, "output.mp4")
```

### Command-line batch exporter

The batch exporter reads a queue of export requests from a Google Spreadsheet and renders them. It requires Google API credentials and additional dependencies (`gspread`, `oauth2client`, `google-api-python-client`).

```bash
# Set environment variables
export BREATHECAM_SECRETS_PATH=/path/to/secrets
export BREATHECAM_EXPORT_DIR=/path/to/exports

# Export the next pending video from a Google Spreadsheet
python -m timemachine_video_export.batch_video_exporter "Spreadsheet Name" --export-next
```

## Development

### Running tests

```bash
pytest tests/
```

Key test files:

- `tests/test_timemachine.py` -- Tests for `TimeMachine`, including `download_video_frame_range` at native resolution and multi-scale comparison. Verifies frames against direct tile downloads.
- `tests/test_video_renderer.py` -- Tests for scaled rendering via `download_scaled_video_frame_range`, including half-size, squeeze, and fractional-pixel-offset cases.
- `tests/test_thumbnail_api.py` -- Tests for URL parsing, thumbnail dimensions, scale, and begin/end time manipulation.
- `tests/test_video_decoder.py` -- Tests for the low-level ffmpeg frame decoder.
- `tests/test_batch_video_exporter.py` -- Integration tests for the Google Sheets batch exporter (requires credentials).

## License

MIT License - CMU CREATE Lab
