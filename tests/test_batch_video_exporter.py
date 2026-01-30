import pytest
from timemachine_video_export import (
    BatchVideoExporter, OutputToStream, OutputToVideo, Thumbnails,
    render_video_from_thumbnail, render_video_site, BreathecamThumbnail, Rectangle,
    TimeMachine, Stopwatch
)
from datetime import datetime
from zoneinfo import ZoneInfo

export_sheet_name = "Batch video exports test sheet"

def test_export_first_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[0])

def test_export_second_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[1])

def test_export_third_video():
    # takes 143 seconds for 1h of video
    # 214 with 5 chunk threads
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[2])

def test_export_shenango_avalon_accan_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[4])

def test_export_shenango_bellevue_achd_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[5])

# def test_export_fourth_video():
#     exporter = BatchVideoExporter("Natisha BreatheCam video exports")
#     exporter.export_video(exporter.df.iloc[3])

def test_export_next_video():
    exporter = BatchVideoExporter("Natisha Breathe Cam video exports")
    exporter.export_next()

def test_noop():
    print("hello from test_noop")

def test_export_edgar_thomson_south():
    # Create start time as 2/1/2025 8am eastern time
    # Create end time as 2/1/2025 8:05am easter
    begin_datetime = datetime(2025, 2, 1, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 1, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))

    render_video_site("Edgar Thomson South",
                 begin_datetime, end_datetime,
                 "test_export_edgar_thomson_south.mp4")

def test_render_video_to_stdout_from_thumbnail():
    # Create start time as 2/1/2025 8am eastern time
    # Create end time as 2/1/2025 8:05am easter
    begin_datetime = datetime(2025, 2, 1, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 1, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))
    site="edgar_thomson_south"
    # Assert begin and end have timezones
    assert begin_datetime.tzinfo is not None, "begin_datetime must have a timezone"
    assert end_datetime.tzinfo is not None, "end_datetime must have a timezone"
    # Assert site matches an attribute in Thumbnails
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail = getattr(Thumbnails, site)().copy()

    thumbnail.set_begin_end_times(begin_datetime, end_datetime)
    assert thumbnail.scale() == (1, 1), "Thumbnail must have a scale of 1:1"

    with open("test_thumbnail_binary.rgb", "wb") as f:
        # Check that the file is created
        output = OutputToStream(f, thumbnail.width, thumbnail.height)
        render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)



def test_clairton_2017_original_size():
    begin_datetime = datetime(2017, 2, 4, 17, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2017, 2, 4, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    render_video_site("Clairton",
                begin_datetime, end_datetime,
                "test_export_clairton_2017_original-size.mp4",
                use_original_full_res=True)



def test_clairton_full_size():
    # Create start time as 2/1/2025 8am eastern time
    # Create end time as 2/1/2025 8:05am easter
    begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 15, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))
    site="clairton"
    # Assert begin and end have timezones
    assert begin_datetime.tzinfo is not None, "begin_datetime must have a timezone"
    assert end_datetime.tzinfo is not None, "end_datetime must have a timezone"
    # Assert site matches an attribute in Thumbnails
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
    # Create start time as 2/15/2025 8am eastern time
    # Create end time as 2/15/2025 8:05am easter
    begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end_datetime = datetime(2025, 2, 15, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))
    site="clairton"
    # Assert begin and end have timezones
    assert begin_datetime.tzinfo is not None, "begin_datetime must have a timezone"
    assert end_datetime.tzinfo is not None, "end_datetime must have a timezone"
    # Assert site matches an attribute in Thumbnails
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail = getattr(Thumbnails, site)().copy()

    thumbnail.set_begin_end_times(begin_datetime, end_datetime)
    thumbnail.set_scale(0.5, 0.5)
    assert thumbnail.scale() == (0.5, 0.5), "Thumbnail must have a scale of 0.5:0.5"

    test_file = "test_outputs/test_clairton_half_size.mp4"

    output = OutputToVideo(test_file, thumbnail.width, thumbnail.height)
    render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)

test_clairton_begin_datetime = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
test_clairton_end_datetime = datetime(2025, 2, 15, 8, 5, 0, tzinfo=ZoneInfo("America/New_York"))

def get_test_clairton_thumbnail() -> BreathecamThumbnail:
    site="clairton"
    # Assert site matches an attribute in Thumbnails
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail: BreathecamThumbnail = getattr(Thumbnails, site)().copy()

    begin_datetime = test_clairton_begin_datetime
    end_datetime = test_clairton_end_datetime
    # Assert begin and end have timezones
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

def test_clairton_10_pct_offset():
    thumbnail = get_test_clairton_thumbnail()
    # Try 10% size, offset by fractional pixels
    thumbnail.width = 6613//20*2
    thumbnail.height = 2717//20*2
    thumbnail.set_view_rect(Rectangle(0.5, 0.25, thumbnail.width*10+0.5, thumbnail.height*10+0.25))

    render_test_clairton_thumbnail(thumbnail, "test_outputs/test_clairton_10_pct_offset.mp4")
