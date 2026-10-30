import numpy as np
import pytest

from ovito_tachyon.export import FORMATS, encode, ffmpeg_exe, frame_list
from ovito_tachyon.image import write_png


def test_frame_list():
    assert frame_list(0, 10, 5) == [0, 5, 10]
    assert frame_list(3, 3) == [3]
    with pytest.raises(ValueError):
        frame_list(5, 1)
    with pytest.raises(ValueError):
        frame_list(0, 5, 0)


def test_formats():
    assert FORMATS == ("png", "sequence", "gif", "mp4")


@pytest.mark.parametrize("fmt", ["gif", "mp4"])
def test_encode(tmp_path, fmt):
    pytest.importorskip("imageio_ffmpeg")
    for i in range(4):
        img = np.full((48, 64, 3), 255, dtype=np.uint8)
        img[10:30, 10 + 8 * i:30 + 8 * i] = (200, 30, 30)
        write_png(tmp_path / f"frame_{i:05d}.png", img)
    out = tmp_path / f"anim.{fmt}"
    encode(tmp_path / "frame_%05d.png", out, fmt, fps=5)
    assert out.stat().st_size > 0
    assert ffmpeg_exe()
