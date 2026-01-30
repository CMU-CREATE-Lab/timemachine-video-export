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

## Configuration

The library uses environment variables for configuration:

- `BREATHECAM_SECRETS_PATH`: Path to the directory containing Google API credentials (default: `./secrets`)
- `BREATHECAM_EXPORT_DIR`: Path to the directory where exported videos are saved (default: `./exports`)

## Usage

### As a library

```python
from timemachine_video_export import TimeMachine, BreathecamThumbnail, Rectangle

# Create a TimeMachine from a URL
tm = TimeMachine("https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2024-10-23.timemachine")

# Download frames
frames = tm.download_video_frame_range(
    start_frame_no=0,
    nframes=15,
    rect=Rectangle(x1=0, y1=0, x2=1920, y2=1080),
    subsample=1
)
```

### Command-line batch exporter

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

## License

MIT License - CMU CREATE Lab
