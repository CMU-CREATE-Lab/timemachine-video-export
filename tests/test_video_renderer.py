import pytest
from timemachine_video_export.video_renderer import (
    OutputToVideo, Thumbnails,
    render_video, render_video_from_thumbnail, render_video_site,
)
from timemachine_video_export import BreathecamThumbnail, Rectangle
from datetime import datetime
from zoneinfo import ZoneInfo


@pytest.mark.slow
def test_export_edgar_thomson_south():
    begin_datetime = datetime(2025, 2, 1, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 1, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))

    render_video_site("Edgar Thomson South",
                 begin_datetime, end_datetime,
                 "test_export_edgar_thomson_south.mp4")


@pytest.mark.slow
def test_clairton_2017_original_size():
    begin_datetime = datetime(2017, 2, 4, 17, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2017, 2, 4, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    render_video_site("Clairton",
                begin_datetime, end_datetime,
                "test_export_clairton_2017_original-size.mp4",
                use_original_full_res=True)


@pytest.mark.slow
def test_clairton_full_size():
    begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 15, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))
    site="clairton"
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail = getattr(Thumbnails, site)().copy()

    thumbnail.set_begin_end_times(begin_datetime, end_datetime)
    thumbnail.set_scale(1, 1)
    assert thumbnail.scale() == (1, 1), "Thumbnail must have a scale of 1:1"

    test_file = "test_outputs/test_clairton_full_size.mp4"

    output = OutputToVideo(test_file, thumbnail.width, thumbnail.height)
    render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)

# Test half-size export (for power of 2 scaling)
# 2/1/2025 seems to not exist
def test_clairton_half_size():
    begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 15, 8, 1, 0, tzinfo=ZoneInfo("America/New_York"))
    site="clairton"
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail = getattr(Thumbnails, site)().copy()

    thumbnail.set_begin_end_times(begin_datetime, end_datetime)
    thumbnail.set_scale(0.5, 0.5)
    assert thumbnail.scale() == (0.5, 0.5), "Thumbnail must have a scale of 0.5:0.5"

    test_file = "test_outputs/test_clairton_half_size.mp4"

    output = OutputToVideo(test_file, thumbnail.width, thumbnail.height)
    render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)

test_clairton_begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
test_clairton_end_datetime = datetime(2025, 2, 15, 8, 1, 0, tzinfo=ZoneInfo("America/New_York"))

def get_test_clairton_thumbnail() -> BreathecamThumbnail:
    site="clairton"
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail: BreathecamThumbnail = getattr(Thumbnails, site)().copy()

    begin_datetime = test_clairton_begin_datetime
    end_datetime = test_clairton_end_datetime
    assert begin_datetime.tzinfo is not None, "begin_datetime must have a timezone"
    assert end_datetime.tzinfo is not None, "end_datetime must have a timezone"
    thumbnail.set_begin_end_times(begin_datetime, end_datetime)

    return thumbnail

def render_test_clairton_thumbnail(thumbnail: BreathecamThumbnail, output_file: str):
    begin_datetime = test_clairton_begin_datetime
    end_datetime = test_clairton_end_datetime

    output = OutputToVideo(output_file, thumbnail.width, thumbnail.height)
    render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)

def test_clairton_squeeze1():
    thumbnail = get_test_clairton_thumbnail()

    thumbnail.set_view_rect(Rectangle(0, 0, 6613, 2717))

    render_test_clairton_thumbnail(thumbnail, "test_outputs/test_clairton_squeeze1.mp4")

# Same output as test_clairton_squeeze1, but constructed from explicit primitives
# (timemachine URL, times, source rect, output size). This is the shape that the
# upcoming command-line tool will accept.
def test_clairton_squeeze1_from_scratch():
    timemachine_root_url = "https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2025-02-15.timemachine"
    begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 15, 8, 1, 0, tzinfo=ZoneInfo("America/New_York"))
    source_rect = Rectangle(0, 0, 6613, 2717)
    output_width = 3840
    output_height = 2160

    test_file = "test_outputs/test_clairton_squeeze1_from_scratch.mp4"
    output = OutputToVideo(test_file, output_width, output_height)
    render_video(
        timemachine_root_url=timemachine_root_url,
        begin_datetime=begin_datetime,
        end_datetime=end_datetime,
        source_rect=source_rect,
        output=output,
    )

def test_clairton_10_pct_offset():
    thumbnail = get_test_clairton_thumbnail()
    # Try 10% size, offset by fractional pixels
    thumbnail.width = 6613//20*2
    thumbnail.height = 2717//20*2
    thumbnail.set_view_rect(Rectangle(0.5, 0.25, thumbnail.width*10+0.5, thumbnail.height*10+0.25))

    render_test_clairton_thumbnail(thumbnail, "test_outputs/test_clairton_10_pct_offset.mp4")
