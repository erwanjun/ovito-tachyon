import numpy as np
import pytest

ovito = pytest.importorskip("ovito")

from ovito.data import DataCollection, Particles, SimulationCell  # noqa: E402
from ovito.pipeline import Pipeline, StaticSource  # noqa: E402
from ovito.modifiers import CreateBondsModifier  # noqa: E402
from ovito.vis import Viewport  # noqa: E402

from ovito_tachyon import TachyonExporter, find_tachyon  # noqa: E402
from ovito_tachyon._binary import TachyonNotFoundError  # noqa: E402


def _pipeline():
    data = DataCollection()
    data.create_cell([[6, 0, 0, 0], [0, 6, 0, 0], [0, 0, 6, 0]], pbc=(True, True, True))
    particles = Particles(count=4)
    particles.create_property("Position", data=[[1, 1, 1], [2.2, 1, 1], [5.5, 1, 1], [3, 3, 3]])
    types = particles.create_property("Particle Type", data=[1, 1, 2, 2])
    types.types.append(ovito.data.ParticleType(id=1, name="A", color=(1, 0, 0), radius=0.5))
    types.types.append(ovito.data.ParticleType(id=2, name="B", color=(0, 0, 1), radius=0.0))
    data.objects.append(particles)
    pipeline = Pipeline(source=StaticSource(data=data))
    pipeline.modifiers.append(CreateBondsModifier(cutoff=1.6))
    return pipeline


def test_build_scene_counts():
    pipeline = _pipeline()
    scene = TachyonExporter().build_scene(pipelines=[pipeline], size=(100, 80))
    # 4 particles + 8 cell corners; bonds: 1-2 and periodic 1-3 => 4 half-cylinders; 12 cell edges
    assert scene.num_objects == 4 + 8 + 4 + 12


def test_zero_width_cell_is_hidden():
    # Like OVITO, a cell constructed directly (line_width 0) is not rendered.
    data = DataCollection()
    data.objects.append(SimulationCell(matrix=[[6, 0, 0, 0], [0, 6, 0, 0], [0, 0, 6, 0]]))
    particles = Particles(count=1)
    particles.create_property("Position", data=[[1, 1, 1]])
    data.objects.append(particles)
    scene = TachyonExporter().build_scene(pipelines=[Pipeline(source=StaticSource(data=data))])
    assert scene.num_objects == 1


def test_viewport_camera():
    pipeline = _pipeline()
    vp = Viewport(type=Viewport.Type.Top, camera_pos=(3, 3, 20), camera_dir=(0, 0, -1), fov=4.0)
    scene = TachyonExporter().build_scene(viewport=vp, pipelines=[pipeline], size=(100, 100))
    assert "projection orthographic" in scene._camera
    assert "updir 0 1 " in scene._camera


def test_render(tmp_path):
    try:
        find_tachyon()
    except TachyonNotFoundError:
        pytest.skip("tachyon executable not available")
    img = TachyonExporter(antialiasing_samples=2, ambient_occlusion_samples=4).render(
        tmp_path / "x.png", pipelines=[_pipeline()], size=(120, 90))
    assert img.shape == (90, 120, 3)
    assert (tmp_path / "x.png").stat().st_size > 0
    assert (img < 250).any()
