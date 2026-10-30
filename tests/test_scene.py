import numpy as np
import pytest

from ovito_tachyon import Material, TachyonScene, find_tachyon
from ovito_tachyon._binary import TachyonNotFoundError, run_tachyon
from ovito_tachyon.image import read_ppm, write_png


def _scene(width=64, height=48):
    s = TachyonScene(width, height, background=(1, 1, 1))
    s.set_camera((0, 0, 10), (0, 0, -1), (0, 1, 0), np.radians(35), perspective=True, antialiasing_samples=0)
    s.add_directional_light((0.2, -0.2, -1), 0.9)
    s.set_shading(shadows=True)
    return s


def _have_tachyon():
    try:
        find_tachyon()
        return True
    except TachyonNotFoundError:
        return False


needs_tachyon = pytest.mark.skipif(not _have_tachyon(), reason="tachyon executable not available")


def test_scene_file_contents(tmp_path):
    s = _scene()
    s.add_spheres([[0, 0, 0], [1, 0, 0]], [0.5, 0.5], [[1, 0, 0], [1, 0, 0]])
    s.add_cylinders([[0, 0, 0]], [[1, 0, 0]], 0.1, (0, 0, 1), transparency=[0.5])
    path = tmp_path / "s.dat"
    s.write(path)
    text = path.read_text()
    assert text.startswith("begin_scene\nresolution 64 48\n")
    assert text.rstrip().endswith("end_scene")
    # identical colours share one texture definition
    assert text.count("texdef") == 2
    assert text.count("sphere center") == 2
    assert "fcylinder base" in text and "opacity 0.502" in text
    # z is mirrored for Tachyon's left-handed frame
    assert "center 0 0 -10" in text
    assert s.num_objects == 3


def test_zero_radius_objects_are_dropped(tmp_path):
    s = _scene()
    s.add_spheres([[0, 0, 0], [1, 1, 1]], [0.0, 1.0], (1, 1, 1))
    assert s.num_objects == 1


def test_camera_requires_valid_up():
    s = TachyonScene(10, 10)
    with pytest.raises(ValueError):
        s.set_camera((0, 0, 0), (0, 0, -1), (0, 0, 1), 0.5)


def test_write_requires_camera(tmp_path):
    with pytest.raises(RuntimeError):
        TachyonScene(10, 10).write(tmp_path / "x.dat")


def test_png_roundtrip(tmp_path):
    img = np.zeros((5, 7, 3), dtype=np.uint8)
    img[1, 2] = (10, 200, 30)
    write_png(tmp_path / "a.png", img)
    data = (tmp_path / "a.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in data


@needs_tachyon
def test_render_sphere(tmp_path):
    s = _scene(80, 60)
    s.add_spheres([[0, 0, 0]], [1.5], (1, 0, 0), material=Material(ambient=0.2))
    s.write(tmp_path / "s.dat")
    run_tachyon(tmp_path / "s.dat", tmp_path / "o.ppm", threads=2)
    img = read_ppm(tmp_path / "o.ppm")
    assert img.shape == (60, 80, 3)
    center = img[30, 40].astype(int)
    corner = img[0, 0].astype(int)
    assert center[0] > 100 and center[1] < 60 and center[2] < 60  # red sphere in the middle
    assert (corner > 240).all()  # white background


@needs_tachyon
def test_image_orientation(tmp_path):
    # A sphere at +x/+y (right-handed, viewed from +z) must show up top-right.
    s = _scene(80, 80)
    s.add_spheres([[2, 2, 0]], [0.8], (0, 0, 1), material=Material(ambient=0.3))
    s.write(tmp_path / "s.dat")
    run_tachyon(tmp_path / "s.dat", tmp_path / "o.ppm")
    img = read_ppm(tmp_path / "o.ppm").astype(int)
    blue = (img[..., 2] > 100) & (img[..., 0] < 100)
    ys, xs = np.nonzero(blue)
    assert len(xs) > 0
    assert xs.mean() > 40 and ys.mean() < 40
