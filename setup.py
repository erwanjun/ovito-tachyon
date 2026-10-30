"""Build hook: compile the vendored Tachyon ray tracer into ovito_tachyon/bin/.

All metadata lives in pyproject.toml. The executable is platform specific, so
wheels are tagged ``py3-none-<platform>``.
"""

import os
import sys
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py

try:
    from setuptools.command.bdist_wheel import bdist_wheel
except ImportError:  # setuptools < 70
    from wheel.bdist_wheel import bdist_wheel

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "tachyon"
# Same object list as Tachyon's unix/Makefile (parvol.c and apitrigeom.c are not built there).
RAY_SOURCES = ["api", "apigeom", "box", "global", "hash", "parallel", "threads", "camera", "render", "trace",
               "grid", "intersect", "sphere", "plane", "ring", "triangle", "cylinder", "quadric", "extvol", "vol",
               "ui", "util", "vector", "shade", "texture", "coordsys", "imap", "light", "imageio", "jpeg",
               "pngfile", "ppm", "psd", "sgirgb", "tgafile", "winbmp"]
DEMO_SOURCES = ["main", "getargs", "parse", "nffparse", "glwin", "spaceball", "trackball", "mgfparse", "ac3dparse"]
EXE = "tachyon.exe" if sys.platform == "win32" else "tachyon"


def compile_tachyon(out_dir: Path, build_temp: Path) -> Path:
    from distutils.ccompiler import new_compiler
    from distutils.sysconfig import customize_compiler

    cc = new_compiler()
    customize_compiler(cc)
    sources = ([str(VENDOR / "src" / f"{n}.c") for n in RAY_SOURCES]
               + [str(VENDOR / "demosrc" / f"{n}.c") for n in DEMO_SOURCES])
    if cc.compiler_type == "msvc":
        macros = [("THR", None), ("WIN32", None), ("_CRT_SECURE_NO_WARNINGS", None)]
        cflags, libs = ["/O2"], []
    else:
        macros = [("THR", None), ("_REENTRANT", None)]
        cflags, libs = ["-O3", "-w"], ["m", "pthread"]
    # Fold the env flags in so `CFLAGS=-arch arm64` etc. from cibuildwheel apply.
    cflags += os.environ.get("CFLAGS", "").split()
    objects = cc.compile(
        sources,
        output_dir=str(build_temp),
        macros=macros,
        include_dirs=[str(VENDOR / "src"), str(VENDOR / "demosrc")],
        extra_postargs=cflags,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    cc.link_executable(objects, "tachyon", output_dir=str(out_dir), libraries=libs,
                       extra_postargs=os.environ.get("LDFLAGS", "").split())
    exe = out_dir / EXE
    if not exe.is_file():
        raise RuntimeError(f"Tachyon build did not produce {exe}")
    exe.chmod(0o755)
    return exe


class BuildPyWithTachyon(build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            target = ROOT / "src" / "ovito_tachyon" / "bin"
        else:
            target = Path(self.build_lib) / "ovito_tachyon" / "bin"
        build_temp = ROOT / "build" / "tachyon-obj"
        exe = compile_tachyon(target, build_temp)
        print(f"built {exe}")


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, plat = super().get_tag()
        return "py3", "none", plat


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


setup(
    distclass=BinaryDistribution,
    cmdclass={"build_py": BuildPyWithTachyon, "bdist_wheel": PlatformWheel},
)
