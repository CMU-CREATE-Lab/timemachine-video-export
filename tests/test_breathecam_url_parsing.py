import datetime

import pytz

from timemachine_video_export import BreathecamThumbnail


BARE_URL = (
    "https://breathecam.org#v=2991,1460,5310,2764,pts"
    "&t=1422.025&ps=50"
    "&bt=20260417181403&et=20260417181503"
    "&startDwell=0&endDwell=0"
    "&d=2026-04-17&s=clairton4&fps=9"
)


def test_bare_breathecam_url_parses_core_fields():
    t = BreathecamThumbnail(BARE_URL)
    assert t.s == "clairton4"
    assert t.d == "2026-04-17"
    assert t.bt == "20260417181403"
    assert t.et == "20260417181503"
    assert t.fps == 9


def test_bare_breathecam_url_view_rect():
    t = BreathecamThumbnail(BARE_URL)
    rect = t.view_rect()
    assert (rect.x1, rect.y1, rect.x2, rect.y2) == (2991.0, 1460.0, 5310.0, 2764.0)


def test_bare_breathecam_url_dimensions_even_rounded():
    t = BreathecamThumbnail(BARE_URL)
    # v-rect width=2319, height=1304; both rounded down to even
    assert t.width == 2318
    assert t.height == 1304


def test_bare_breathecam_url_timemachine_root_url():
    t = BreathecamThumbnail(BARE_URL)
    assert t.timemachine_root_url() == (
        "https://tiles.cmucreatelab.org/ecam/timemachines/clairton4/2026-04-17.timemachine"
    )


def test_bare_breathecam_url_begin_end_times_in_camera_tz():
    t = BreathecamThumbnail(BARE_URL)
    et_tz = pytz.timezone("America/New_York")
    # 2026-04-17 18:14:03 UTC == 14:14:03 EDT (UTC-4 during DST)
    assert t.begin_time_in_camera_timezone() == et_tz.localize(
        datetime.datetime(2026, 4, 17, 14, 14, 3)
    )
    assert t.end_time_in_camera_timezone() == et_tz.localize(
        datetime.datetime(2026, 4, 17, 14, 15, 3)
    )
