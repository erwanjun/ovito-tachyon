"""Render OVITO pipelines with a bundled, standalone Tachyon ray tracer."""

__version__ = "0.1.1"

from ._binary import TachyonNotFoundError, find_tachyon
from .exporter import TachyonExporter, render
from .scene import Material, TachyonScene

__all__ = ["TachyonExporter", "render", "TachyonScene", "Material", "find_tachyon", "TachyonNotFoundError"]
