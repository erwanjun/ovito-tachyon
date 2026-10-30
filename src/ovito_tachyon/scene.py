"""Writer for Tachyon scene description files (.dat).

This module does not depend on OVITO. All coordinates passed in are in a
right-handed world frame (OVITO's convention); Tachyon is left-handed, so the
z component of every point and direction is negated when the file is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

_CHUNK = 50_000


@dataclass(frozen=True)
class Material:
    """Surface parameters of Tachyon's built-in Phong texture.

    The defaults were fitted pixel by pixel to OVITO's TachyonRenderer with its
    default settings; raise ``ambient`` for a brighter image.
    """

    ambient: float = 0.3
    diffuse: float = 0.8
    specular: float = 0.0
    phong: float = 0.0
    phong_size: float = 40.0


def _as_vec3(v) -> np.ndarray:
    a = np.asarray(v, dtype=float).reshape(3)
    if not np.all(np.isfinite(a)):
        raise ValueError(f"non-finite vector: {v!r}")
    return a


def _to_tachyon(points: np.ndarray) -> np.ndarray:
    out = np.array(points, dtype=float, copy=True)
    out[..., 2] *= -1.0
    return out


def _broadcast(values, n: int, width: int, name: str) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if width == 1:
        a = np.broadcast_to(a.reshape(-1) if a.ndim else a, (n,))
    else:
        a = np.broadcast_to(a, (n, width))
    if a.shape[0] != n:
        raise ValueError(f"{name}: expected {n} entries, got {a.shape[0]}")
    return np.ascontiguousarray(a)


class TachyonScene:
    """Collects geometry, lights and camera settings and writes a .dat file."""

    def __init__(self, width: int, height: int, background: Sequence[float] = (1.0, 1.0, 1.0)):
        if width <= 0 or height <= 0:
            raise ValueError("image size must be positive")
        self.width = int(width)
        self.height = int(height)
        self.background = tuple(float(c) for c in background)
        self._camera: Optional[str] = None
        self._lights: list[str] = []
        self._shader = "full"
        self._ao: Optional[tuple[int, float, float]] = None
        self._textures: dict[tuple, str] = {}
        self._texdefs: list[str] = []
        self._chunks: list[tuple[str, np.ndarray]] = []
        self.num_objects = 0

    # ---------------------------------------------------------------- camera
    def set_camera(
        self,
        position,
        direction,
        up,
        fov: float,
        perspective: bool = True,
        antialiasing_samples: int = 12,
        raydepth: int = 10,
        dof: Optional[tuple[float, float]] = None,
    ) -> None:
        """Configure the camera using OVITO's conventions.

        ``fov`` is the full vertical view angle in radians for perspective
        views, or half the visible height in world units for parallel views.
        ``dof`` is an optional ``(focal_length, aperture)`` pair.
        """
        pos = _as_vec3(position)
        d = _as_vec3(direction)
        u = _as_vec3(up)
        if np.linalg.norm(d) == 0:
            raise ValueError("camera direction must be non-zero")
        d = d / np.linalg.norm(d)
        u = u - np.dot(u, d) * d
        if np.linalg.norm(u) < 1e-9:
            raise ValueError("camera up vector is parallel to the view direction")
        u = u / np.linalg.norm(u)

        aspect = self.height / self.width
        if perspective:
            top = float(np.tan(0.5 * fov))
        else:
            top = float(fov)
        right = top / aspect

        if dof is not None and perspective:
            focal_length, aperture = (float(x) for x in dof)
            # Tachyon puts the image plane at the focal distance.
            top *= focal_length
            right *= focal_length
            proj = f"projection perspective_dof focallength {focal_length:.7g} aperture {aperture:.7g}"
        else:
            proj = "projection " + ("perspective" if perspective else "orthographic")

        tp, td, tu = _to_tachyon(pos), _to_tachyon(d), _to_tachyon(u)
        self._camera = (
            "camera\n"
            f"  {proj}\n"
            "  zoom 1.0\n"
            "  aspectratio 1.0\n"
            f"  antialiasing {max(int(antialiasing_samples), 0)}\n"
            f"  raydepth {max(int(raydepth), 1)}\n"
            f"  center {tp[0]:.9g} {tp[1]:.9g} {tp[2]:.9g}\n"
            f"  viewdir {td[0]:.9g} {td[1]:.9g} {td[2]:.9g}\n"
            f"  updir {tu[0]:.9g} {tu[1]:.9g} {tu[2]:.9g}\n"
            f"  frustum {-right:.9g} {right:.9g} {-top:.9g} {top:.9g}\n"
            "end_camera\n"
        )

    # ---------------------------------------------------------------- lights
    def add_directional_light(self, direction, intensity: float = 1.0, color=(1.0, 1.0, 1.0)) -> None:
        """Add a light travelling along ``direction`` (world coordinates)."""
        d = _to_tachyon(_as_vec3(direction))
        c = np.clip(np.asarray(color, dtype=float) * intensity, 0.0, None)
        self._lights.append(
            f"directional_light direction {d[0]:.7g} {d[1]:.7g} {d[2]:.7g} "
            f"color {c[0]:.5g} {c[1]:.5g} {c[2]:.5g}\n"
        )

    def set_shading(self, shadows: bool = True, ambient_occlusion: Optional[tuple[int, float, float]] = None) -> None:
        """``ambient_occlusion`` is ``(samples, brightness, rescale_direct)`` or None.

        Tachyon only computes ambient occlusion in its full shader, which always
        casts shadows, so AO implies shadows.
        """
        self._ao = ambient_occlusion
        self._shader = "full" if (shadows or ambient_occlusion) else "medium"

    # -------------------------------------------------------------- textures
    def _texture_ids(self, colors: np.ndarray, opacity: np.ndarray, material: Material) -> np.ndarray:
        q = np.empty((len(colors), 4), dtype=np.int64)
        q[:, :3] = np.rint(np.clip(colors, 0.0, 1.0) * 255.0)
        q[:, 3] = np.rint(np.clip(opacity, 0.0, 1.0) * 255.0)
        keys = ((q[:, 0] << 24) | (q[:, 1] << 16) | (q[:, 2] << 8) | q[:, 3])
        uniq, inverse = np.unique(keys, return_inverse=True)
        ids = np.empty(len(uniq), dtype=np.int64)
        for i, k in enumerate(uniq.tolist()):
            ids[i] = self._texture_id(k, material)
        return ids[inverse.reshape(-1)]

    def _texture_id(self, key: int, m: Material) -> int:
        full = (key, m)
        name = self._textures.get(full)
        if name is None:
            r, g, b, a = (key >> 24) & 255, (key >> 16) & 255, (key >> 8) & 255, key & 255
            name = f"t{len(self._textures)}"
            self._textures[full] = name
            self._texdefs.append(
                f"texdef {name} ambient {m.ambient:.4g} diffuse {m.diffuse:.4g} "
                f"specular {m.specular:.4g} opacity {a / 255.0:.4g}\n"
                f"  phong plastic {m.phong:.4g} phong_size {m.phong_size:.4g}\n"
                f"  color {r / 255.0:.4g} {g / 255.0:.4g} {b / 255.0:.4g}\n"
                "  texfunc 0\n"
            )
        return int(name[1:])

    # -------------------------------------------------------------- geometry
    def add_spheres(self, centers, radii, colors, transparency=None, material: Material = Material()) -> None:
        c = np.asarray(centers, dtype=float).reshape(-1, 3)
        n = len(c)
        if n == 0:
            return
        r = _broadcast(radii, n, 1, "radii")
        col = _broadcast(colors, n, 3, "colors")
        op = 1.0 - _broadcast(0.0 if transparency is None else transparency, n, 1, "transparency")
        keep = r > 0
        tex = self._texture_ids(col[keep], op[keep], material)
        rows = np.column_stack([_to_tachyon(c[keep]), r[keep], tex])
        self._chunks.append(("sphere center %.7g %.7g %.7g rad %.7g t%d\n", rows))
        self.num_objects += len(rows)

    def add_cylinders(self, base, apex, radii, colors, transparency=None, material: Material = Material()) -> None:
        """Add open cylinders running from ``base`` to ``apex``."""
        b = np.asarray(base, dtype=float).reshape(-1, 3)
        a = np.asarray(apex, dtype=float).reshape(-1, 3)
        if b.shape != a.shape:
            raise ValueError("base and apex must have the same shape")
        n = len(b)
        if n == 0:
            return
        r = _broadcast(radii, n, 1, "radii")
        col = _broadcast(colors, n, 3, "colors")
        op = 1.0 - _broadcast(0.0 if transparency is None else transparency, n, 1, "transparency")
        keep = (r > 0) & (np.linalg.norm(a - b, axis=1) > 0)
        tex = self._texture_ids(col[keep], op[keep], material)
        rows = np.column_stack([_to_tachyon(b[keep]), _to_tachyon(a[keep]), r[keep], tex])
        self._chunks.append(("fcylinder base %.7g %.7g %.7g apex %.7g %.7g %.7g rad %.7g t%d\n", rows))
        self.num_objects += len(rows)

    # ----------------------------------------------------------------- output
    def write(self, path) -> None:
        if self._camera is None:
            raise RuntimeError("set_camera() must be called before write()")
        bg = self.background
        with open(path, "w", encoding="ascii") as f:
            f.write("begin_scene\n")
            f.write(f"resolution {self.width} {self.height}\n")
            f.write(f"shader_mode {self._shader}\n")
            if self._ao is not None:
                samples, brightness, rescale = self._ao
                f.write(
                    f"  ambient_occlusion ambient_color {brightness:.4g} {brightness:.4g} {brightness:.4g} "
                    f"rescale_direct {rescale:.4g} samples {int(samples)}\n"
                )
            f.write("end_shader_mode\n")
            f.write(self._camera)
            f.write(f"background {bg[0]:.4g} {bg[1]:.4g} {bg[2]:.4g}\n")
            f.writelines(self._lights)
            f.writelines(self._texdefs)
            for fmt, rows in self._chunks:
                for start in range(0, len(rows), _CHUNK):
                    block = rows[start:start + _CHUNK]
                    f.write((fmt * len(block)) % tuple(block.ravel().tolist()))
            f.write("end_scene\n")
