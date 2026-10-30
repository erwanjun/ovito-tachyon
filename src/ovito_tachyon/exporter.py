"""Turn OVITO pipeline output and a Viewport camera into a Tachyon rendering."""

from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

from ._binary import run_tachyon
from .image import read_ppm, write_png
from .scene import Material, TachyonScene

_DEFAULT_PARTICLE_COLOR = (0.97, 0.97, 0.97)
_SELECTION_COLOR = (1.0, 0.0, 0.0)
# Light direction in camera space (x right, y up, -z forward), as in OVITO.
_CAMERA_LIGHT = (0.2, -0.2, -1.0)


class TachyonExporter:
    """Render OVITO scenes with an external Tachyon executable.

    The rendering parameters mirror those of :class:`ovito.vis.TachyonRenderer`.
    """

    def __init__(
        self,
        antialiasing: bool = True,
        antialiasing_samples: int = 12,
        ambient_occlusion: bool = True,
        ambient_occlusion_brightness: float = 0.8,
        ambient_occlusion_samples: int = 12,
        direct_light: bool = True,
        direct_light_intensity: float = 0.9,
        shadows: bool = True,
        depth_of_field: bool = False,
        focal_length: float = 40.0,
        aperture: float = 0.01,
        max_ray_recursion: int = 10,
        material: Optional[Material] = None,
        threads: Optional[int] = None,
    ):
        self.antialiasing = antialiasing
        self.antialiasing_samples = antialiasing_samples
        self.ambient_occlusion = ambient_occlusion
        self.ambient_occlusion_brightness = ambient_occlusion_brightness
        self.ambient_occlusion_samples = ambient_occlusion_samples
        self.direct_light = direct_light
        self.direct_light_intensity = direct_light_intensity
        self.shadows = shadows
        self.depth_of_field = depth_of_field
        self.focal_length = focal_length
        self.aperture = aperture
        self.max_ray_recursion = max_ray_recursion
        self.material = material
        self.threads = threads
        # Fraction of direct light kept when ambient occlusion is on.
        self.ao_rescale_direct = 0.2

    # ------------------------------------------------------------------ API
    def render(
        self,
        filename=None,
        viewport=None,
        size: Sequence[int] = (640, 480),
        frame: int = 0,
        background: Sequence[float] = (1.0, 1.0, 1.0),
        pipelines=None,
        zoom_all: Optional[bool] = None,
        scene_file=None,
        verbose: bool = False,
    ) -> np.ndarray:
        """Render one frame and return it as an ``(h, w, 3)`` uint8 array.

        ``filename`` may end in ``.png`` or ``.ppm``. ``pipelines`` defaults to
        all pipelines in ``ovito.scene``. Without a ``viewport`` a perspective
        view along (-1, -1, -1) is used. ``zoom_all`` refits the camera
        distance to the rendered geometry (default: only when no viewport is
        given). ``scene_file`` keeps a copy of the generated .dat file.
        """
        scene = self.build_scene(viewport, size, frame, background, pipelines, zoom_all)
        tmp = tempfile.mkdtemp(prefix="ovito_tachyon_")
        try:
            dat = os.path.join(tmp, "scene.dat")
            ppm = os.path.join(tmp, "image.ppm")
            scene.write(dat)
            if scene_file is not None:
                shutil.copyfile(dat, scene_file)
            run_tachyon(dat, ppm, threads=self.threads, verbose=verbose)
            image = read_ppm(ppm)
            if filename is not None:
                ext = Path(filename).suffix.lower()
                if ext == ".png":
                    write_png(filename, image)
                elif ext == ".ppm":
                    shutil.copyfile(ppm, filename)
                else:
                    raise ValueError(f"unsupported output format {ext!r}; use .png or .ppm")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return image

    def render_animation(self, filename_pattern: str, frames: Iterable[int], **kwargs) -> list[str]:
        """Render several frames; ``filename_pattern`` is formatted with the frame number,
        e.g. ``"frames/img_{:04d}.png"``."""
        written = []
        for frame in frames:
            name = filename_pattern.format(frame)
            Path(name).parent.mkdir(parents=True, exist_ok=True)
            self.render(name, frame=frame, **kwargs)
            written.append(name)
        return written

    def build_scene(
        self,
        viewport=None,
        size: Sequence[int] = (640, 480),
        frame: int = 0,
        background: Sequence[float] = (1.0, 1.0, 1.0),
        pipelines=None,
        zoom_all: Optional[bool] = None,
    ) -> TachyonScene:
        width, height = int(size[0]), int(size[1])
        scene = TachyonScene(width, height, background)
        material = self.material or Material()

        bounds = _Bounds()
        for pipeline in _resolve_pipelines(pipelines):
            data = pipeline.compute(frame)
            _add_particles_and_bonds(scene, data, material, bounds)
            _add_cell(scene, data, material, bounds)

        cam = _camera_from_viewport(viewport)
        if zoom_all if zoom_all is not None else viewport is None:
            _fit_camera(cam, bounds, width, height)
        if not cam["perspective"] and not bounds.empty:
            # Tachyon starts parallel rays at the camera plane; move it behind the scene.
            center, radius = bounds.sphere()
            dist = np.dot(cam["pos"] - center, cam["dir"])
            cam["pos"] = cam["pos"] - cam["dir"] * (dist + 2.0 * radius)

        samples = self.antialiasing_samples if self.antialiasing else 0
        dof = (self.focal_length, self.aperture) if self.depth_of_field else None
        scene.set_camera(cam["pos"], cam["dir"], cam["up"], cam["fov"], cam["perspective"],
                         antialiasing_samples=samples, raydepth=self.max_ray_recursion, dof=dof)

        if self.direct_light:
            right = np.cross(cam["dir"], cam["up"])
            right /= np.linalg.norm(right)
            up = np.cross(right, cam["dir"])
            lx, ly, lz = _CAMERA_LIGHT
            scene.add_directional_light(lx * right + ly * up - lz * cam["dir"], self.direct_light_intensity)
        if self.ambient_occlusion:
            if self.direct_light and not self.shadows:
                warnings.warn("Tachyon cannot render ambient occlusion without shadows; shadows stay on.")
            scene.set_shading(ambient_occlusion=(self.ambient_occlusion_samples,
                                                 self.ambient_occlusion_brightness,
                                                 self.ao_rescale_direct if self.direct_light else 1.0))
        else:
            scene.set_shading(shadows=self.shadows and self.direct_light)
        return scene


def render(filename=None, **kwargs) -> np.ndarray:
    """Shortcut: ``render("out.png", viewport=vp, size=(800, 600), ambient_occlusion=False)``.

    Keyword arguments are split between :class:`TachyonExporter` and
    :meth:`TachyonExporter.render`.
    """
    render_keys = {"viewport", "size", "frame", "background", "pipelines", "zoom_all", "scene_file", "verbose"}
    render_args = {k: kwargs.pop(k) for k in list(kwargs) if k in render_keys}
    return TachyonExporter(**kwargs).render(filename, **render_args)


# ---------------------------------------------------------------- internals
class _Bounds:
    def __init__(self):
        self.lo = np.full(3, np.inf)
        self.hi = np.full(3, -np.inf)

    def add(self, points: np.ndarray, pad=0.0) -> None:
        if len(points) == 0:
            return
        pad = np.asarray(pad, dtype=float).reshape(-1, 1) if np.ndim(pad) else pad
        self.lo = np.minimum(self.lo, (points - pad).min(axis=0))
        self.hi = np.maximum(self.hi, (points + pad).max(axis=0))

    @property
    def empty(self) -> bool:
        return not np.all(self.hi >= self.lo)

    def sphere(self) -> tuple[np.ndarray, float]:
        center = 0.5 * (self.lo + self.hi)
        return center, max(0.5 * float(np.linalg.norm(self.hi - self.lo)), 1e-6)


def _resolve_pipelines(pipelines) -> list:
    if pipelines is None:
        from ovito import scene as ovito_scene
        return list(ovito_scene.pipelines)
    if hasattr(pipelines, "compute"):
        return [pipelines]
    return list(pipelines)


def _camera_from_viewport(vp) -> dict:
    if vp is None:
        return {"pos": np.zeros(3), "dir": _unit((-1.0, -1.0, -1.0)), "up": np.array([0.0, 0.0, 1.0]),
                "fov": np.radians(35.0), "perspective": True}
    from ovito.vis import Viewport
    direction = _unit(vp.camera_dir)
    up = np.asarray(getattr(vp, "camera_up", (0.0, 0.0, 0.0)), dtype=float)
    if np.linalg.norm(up) == 0:
        z = np.array([0.0, 0.0, 1.0])
        up = np.array([0.0, 1.0, 0.0]) if np.linalg.norm(np.cross(direction, z)) < 1e-6 else z
    return {"pos": np.asarray(vp.camera_pos, dtype=float), "dir": direction, "up": up,
            "fov": float(vp.fov), "perspective": vp.type == Viewport.Type.Perspective}


def _fit_camera(cam: dict, bounds: _Bounds, width: int, height: int) -> None:
    if bounds.empty:
        return
    center, radius = bounds.sphere()
    aspect = height / width
    if cam["perspective"]:
        half_v = 0.5 * cam["fov"]
        half_h = np.arctan(np.tan(half_v) / aspect)
        dist = radius / np.sin(min(half_v, half_h))
    else:
        cam["fov"] = radius * max(1.0, aspect)
        dist = 2.0 * radius
    cam["pos"] = center - cam["dir"] * dist


def _unit(v) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    n = np.linalg.norm(a)
    if n == 0:
        raise ValueError("zero-length direction vector")
    return a / n


def _vis_enabled(vis) -> bool:
    return vis is not None and getattr(vis, "enabled", True)


def _per_type(type_property, attr: str, default) -> np.ndarray:
    """Per-element value of a type attribute (e.g. ParticleType.radius)."""
    table = {t.id: getattr(t, attr, default) for t in getattr(type_property, "types", [])}
    uniq, inverse = np.unique(np.asarray(type_property), return_inverse=True)
    values = np.array([table.get(int(i), default) for i in uniq], dtype=float)
    return values[inverse.reshape(-1)]


def _particle_radii(particles, vis) -> np.ndarray:
    n = particles.count
    radii = np.full(n, float(vis.radius))
    if particles.particle_types is not None:
        typed = _per_type(particles.particle_types, "radius", 0.0)
        radii = np.where(typed > 0, typed, radii)
    if "Radius" in particles:
        explicit = np.asarray(particles["Radius"], dtype=float)
        radii = np.where(explicit > 0, explicit, radii)
    scaling = getattr(vis, "scaling", getattr(vis, "radius_scaling", 1.0))
    return radii * float(scaling)


def _particle_colors(particles) -> np.ndarray:
    n = particles.count
    if "Color" in particles:
        return np.asarray(particles["Color"], dtype=float).reshape(n, 3)
    if particles.particle_types is not None:
        return _per_type(particles.particle_types, "color", _DEFAULT_PARTICLE_COLOR).reshape(n, 3)
    return np.tile(_DEFAULT_PARTICLE_COLOR, (n, 1))


def _add_particles_and_bonds(scene: TachyonScene, data, material: Material, bounds: _Bounds) -> None:
    particles = getattr(data, "particles", None)
    if particles is None or particles.count == 0:
        return
    pos = np.asarray(particles.positions, dtype=float)
    colors = _particle_colors(particles)
    vis = particles.vis

    if _vis_enabled(vis):
        shape = getattr(vis, "shape", None)
        if shape is not None and getattr(shape, "name", "Sphere") != "Sphere":
            warnings.warn(f"particle shape {shape.name} is rendered as spheres")
        radii = _particle_radii(particles, vis)
        shown = colors
        if "Selection" in particles:
            sel = np.asarray(particles["Selection"]) != 0
            if sel.any():
                shown = colors.copy()
                shown[sel] = _SELECTION_COLOR
        transparency = particles["Transparency"] if "Transparency" in particles else None
        scene.add_spheres(pos, radii, shown, transparency, material)
        bounds.add(pos, radii)

    bonds = getattr(particles, "bonds", None)
    if bonds is None or bonds.count == 0 or not _vis_enabled(bonds.vis):
        return
    bvis = bonds.vis
    topo = np.asarray(bonds.topology, dtype=np.int64)
    a, b = topo[:, 0], topo[:, 1]
    delta = pos[b] - pos[a]
    if "Periodic Image" in bonds and data.cell is not None:
        cell = np.asarray(data.cell)[:, :3]
        delta = delta + np.asarray(bonds.pbc_vectors, dtype=float) @ cell.T
    mid_a = pos[a] + 0.5 * delta
    mid_b = pos[b] - 0.5 * delta

    color_a, color_b = _bond_colors(bonds, bvis, colors, a, b)
    radius = 0.5 * float(bvis.width)
    transparency = bonds["Transparency"] if "Transparency" in bonds else None
    scene.add_cylinders(np.vstack([pos[a], pos[b]]), np.vstack([mid_a, mid_b]), radius,
                        np.vstack([color_a, color_b]),
                        None if transparency is None else np.concatenate([transparency, transparency]),
                        material)


def _bond_colors(bonds, bvis, particle_colors, a, b):
    n = bonds.count
    if "Color" in bonds:
        c = np.asarray(bonds["Color"], dtype=float).reshape(n, 3)
        return c, c
    mode = getattr(bvis, "coloring_mode", None)
    mode_name = getattr(mode, "name", None)
    if mode_name is None:  # OVITO < 3.10
        mode_name = "ByParticle" if getattr(bvis, "use_particle_colors", True) else "Uniform"
    if mode_name == "ByParticle":
        return particle_colors[a], particle_colors[b]
    if mode_name == "ByBondType" and getattr(bonds, "bond_types", None) is not None:
        c = _per_type(bonds.bond_types, "color", tuple(bvis.color)).reshape(n, 3)
        return c, c
    c = np.tile(np.asarray(bvis.color, dtype=float), (n, 1))
    return c, c


def _add_cell(scene: TachyonScene, data, material: Material, bounds: _Bounds) -> None:
    cell = getattr(data, "cell", None)
    if cell is None or not _vis_enabled(cell.vis) or not getattr(cell.vis, "render_cell", True):
        return
    # OVITO uses line_width as the radius of the cell cylinders in ray-traced images;
    # a cell constructed directly in Python has width 0 and is not rendered.
    width = float(getattr(cell.vis, "line_width", 0.0))
    if width <= 0:
        return
    m = np.asarray(cell, dtype=float)
    origin, va, vb, vc = m[:, 3], m[:, 0], m[:, 1], m[:, 2]
    if getattr(cell, "is2D", False):
        vc = np.zeros(3)
    corners = np.array([origin + i * va + j * vb + k * vc for k in (0, 1) for j in (0, 1) for i in (0, 1)])
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    if getattr(cell, "is2D", False):
        corners, edges = corners[:4], edges[:2] + edges[4:6]
    color = tuple(getattr(cell.vis, "rendering_color", (0.0, 0.0, 0.0)))
    e = np.array(edges)
    scene.add_cylinders(corners[e[:, 0]], corners[e[:, 1]], width, color, None, material)
    scene.add_spheres(corners, width, color, None, material)
    bounds.add(corners, width)
