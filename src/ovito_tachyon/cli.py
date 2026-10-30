"""Command line entry point: ``ovito-tachyon dump.lammpstrj -o image.png``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from ._binary import find_tachyon
from .exporter import TachyonExporter

_VIEW_DIRS = {
    "perspective": (-1.0, -1.0, -1.0),
    "ortho": (-1.0, -1.0, -1.0),
    "top": (0.0, 0.0, -1.0),
    "bottom": (0.0, 0.0, 1.0),
    "front": (0.0, 1.0, 0.0),
    "back": (0.0, -1.0, 0.0),
    "left": (1.0, 0.0, 0.0),
    "right": (-1.0, 0.0, 0.0),
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ovito-tachyon", description="Render a simulation file with Tachyon.")
    p.add_argument("input", nargs="?", help="any file OVITO can import (LAMMPS dump/data, XYZ, POSCAR, ...)")
    p.add_argument("-o", "--output", default="render.png", help="output image (.png or .ppm)")
    p.add_argument("--size", nargs=2, type=int, default=(1600, 1200), metavar=("W", "H"))
    p.add_argument("--frame", type=int, default=0, help="animation frame; -1 = last")
    p.add_argument("--view", choices=sorted(_VIEW_DIRS), default="perspective")
    p.add_argument("--dir", nargs=3, type=float, metavar=("X", "Y", "Z"), help="custom view direction")
    p.add_argument("--background", nargs=3, type=float, default=(1.0, 1.0, 1.0), metavar=("R", "G", "B"))
    p.add_argument("--no-ao", action="store_true", help="disable ambient occlusion")
    p.add_argument("--no-shadows", action="store_true")
    p.add_argument("--aa-samples", type=int, default=12)
    p.add_argument("--ao-samples", type=int, default=12)
    p.add_argument("--threads", type=int)
    p.add_argument("--scene-file", help="also save the generated Tachyon scene (.dat)")
    p.add_argument("--which", action="store_true", help="print the Tachyon executable in use and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    if args.which:
        print(find_tachyon())
        return 0
    if not args.input:
        p.error("an input file is required")

    from ovito.io import import_file
    from ovito.vis import Viewport

    pipeline = import_file(args.input)
    frame = args.frame
    if frame < 0:
        frame += pipeline.source.num_frames

    vp = Viewport(
        type=Viewport.Type.Perspective if args.view == "perspective" else Viewport.Type.Ortho,
        camera_dir=tuple(args.dir) if args.dir else _VIEW_DIRS[args.view],
    )
    exporter = TachyonExporter(
        antialiasing_samples=args.aa_samples,
        ambient_occlusion=not args.no_ao,
        ambient_occlusion_samples=args.ao_samples,
        shadows=not args.no_shadows,
        threads=args.threads,
    )
    exporter.render(args.output, viewport=vp, size=args.size, frame=frame, background=args.background,
                    pipelines=[pipeline], zoom_all=True, scene_file=args.scene_file)
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
