"""Render packaging/icon.png (1024x1024) with the bundled Tachyon. Run once; the PNG is committed."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ovito_tachyon import Material, TachyonScene
from ovito_tachyon._binary import run_tachyon
from ovito_tachyon.image import read_ppm

HERE = Path(__file__).resolve().parent
SIZE = 1024

scene = TachyonScene(SIZE, SIZE, background=(0.09, 0.09, 0.09))
scene.set_camera((0, -9, 0), (0, 1, 0), (0, 0, 1), np.radians(30), antialiasing_samples=16)
scene.add_directional_light((0.4, 1.0, -0.6), 0.9)
scene.set_shading(ambient_occlusion=(32, 0.8, 0.2))
spheres = [((-0.9, 0, -0.55), 1.0, (0.40, 0.40, 1.00)), ((0.95, 0.3, -0.45), 0.9, (1.00, 0.40, 0.40)),
           ((0.05, -0.4, 0.95), 0.75, (1.00, 0.85, 0.10))]
for center, radius, color in spheres:
    scene.add_spheres([center], radius, color, material=Material(ambient=0.3, phong=0.4))
scene.write(HERE / "icon.dat")
run_tachyon(HERE / "icon.dat", HERE / "icon.ppm")
img = Image.fromarray(read_ppm(HERE / "icon.ppm")).convert("RGBA")
(HERE / "icon.dat").unlink()
(HERE / "icon.ppm").unlink()

# macOS-style rounded square with a transparent margin
mask = Image.new("L", (SIZE, SIZE), 0)
pad = 100
ImageDraw.Draw(mask).rounded_rectangle((pad, pad, SIZE - pad, SIZE - pad), radius=185, fill=255)
inner = img.resize((SIZE - 2 * pad, SIZE - 2 * pad), Image.LANCZOS)
out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
out.paste(inner, (pad, pad))
out.putalpha(mask)
out.save(HERE / "icon.png")
print(HERE / "icon.png")
