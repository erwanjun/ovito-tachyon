"""Render a LAMMPS dump with ovito-tachyon.

    python render_dump.py path/to/dump.lammpstrj out.png
"""

import sys

from ovito.io import import_file
from ovito.modifiers import CommonNeighborAnalysisModifier
from ovito.vis import Viewport

from ovito_tachyon import TachyonExporter

pipeline = import_file(sys.argv[1])
pipeline.modifiers.append(CommonNeighborAnalysisModifier())
pipeline.add_to_scene()

vp = Viewport(type=Viewport.Type.Perspective, camera_dir=(-1, -0.6, -0.5))
vp.zoom_all(size=(1600, 1200))

exporter = TachyonExporter(ambient_occlusion_samples=16, antialiasing_samples=16)
exporter.render(sys.argv[2] if len(sys.argv) > 2 else "render.png", viewport=vp, size=(1600, 1200),
                frame=pipeline.source.num_frames - 1)
