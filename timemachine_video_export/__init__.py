"""TimeMachine Video Export - A library for exporting videos from Breathecam timelapse cameras."""

from .rectangle import Rectangle
from .stopwatch import Stopwatch
from .thumbnail_api import Thumbnail, BreathecamThumbnail
from .video_decoder import decode_video_frames
from .timemachine import TimeMachine, CAMERAS
from .batch_video_exporter import (
    BatchVideoExporter,
    Thumbnails,
    OutputToStream,
    OutputToVideo,
    render_video_site,
    render_video_from_thumbnail,
    BREATHECAM_SECRETS_PATH,
    BREATHECAM_EXPORT_DIR,
)

__all__ = [
    # rectangle
    "Rectangle",
    # stopwatch
    "Stopwatch",
    # thumbnail_api
    "Thumbnail",
    "BreathecamThumbnail",
    # video_decoder
    "decode_video_frames",
    # timemachine
    "TimeMachine",
    "CAMERAS",
    # batch_video_exporter
    "BatchVideoExporter",
    "Thumbnails",
    "OutputToStream",
    "OutputToVideo",
    "render_video_site",
    "render_video_from_thumbnail",
    "BREATHECAM_SECRETS_PATH",
    "BREATHECAM_EXPORT_DIR",
]
