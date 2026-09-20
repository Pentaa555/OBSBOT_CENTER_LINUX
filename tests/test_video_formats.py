from app.video_formats import (
    FormatGroup, VideoMode, best_fps_for_resolution, parse_formats,
)

# A trimmed but representative slice of real `v4l2-ctl --list-formats-ext`
# output from the OBSBOT Tiny, covering MJPG (60fps) and YUYV (low fps).
SAMPLE_OUTPUT = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
"""


def test_parses_all_format_groups():
    groups = parse_formats(SAMPLE_OUTPUT)
    assert [g.fourcc for g in groups] == ["MJPG", "YUYV"]
    assert groups[0].description == "Motion-JPEG, compressed"


def test_parses_modes_with_resolution_and_fps():
    groups = parse_formats(SAMPLE_OUTPUT)
    mjpg = groups[0]
    assert VideoMode("MJPG", 1280, 720, 60.0) in mjpg.modes
    assert VideoMode("MJPG", 1280, 720, 30.0) in mjpg.modes
    assert VideoMode("MJPG", 1920, 1080, 30.0) in mjpg.modes
    # 1080p never advertises 60fps on this camera.
    assert VideoMode("MJPG", 1920, 1080, 60.0) not in mjpg.modes


def test_yuyv_is_low_fps():
    groups = parse_formats(SAMPLE_OUTPUT)
    yuyv = groups[1]
    assert yuyv.modes == [VideoMode("YUYV", 1280, 720, 10.0)]


def test_best_fps_for_resolution_scans_all_formats():
    groups = parse_formats(SAMPLE_OUTPUT)
    assert best_fps_for_resolution(groups, 1280, 720) == 60.0
    assert best_fps_for_resolution(groups, 1920, 1080) == 30.0
    assert best_fps_for_resolution(groups, 640, 480) == 0.0


def test_empty_output_yields_no_groups():
    assert parse_formats("") == []


def test_video_mode_str_is_human_readable():
    assert str(VideoMode("MJPG", 1280, 720, 60.0)) == "1280x720 @ 60fps (MJPG)"
