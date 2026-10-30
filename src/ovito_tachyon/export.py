"""Render frame ranges to images, GIF or MP4 (video encoding via imageio-ffmpeg)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional, Sequence

from .exporter import TachyonExporter

FORMATS = ("png", "sequence", "gif", "mp4")

# progress(done, total, message) -> False to cancel
ProgressCallback = Callable[[int, int, str], bool]


class ExportCancelled(Exception):
    pass


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("GIF/MP4 export needs the imageio-ffmpeg package") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def frame_list(first: int, last: int, step: int = 1) -> list[int]:
    if step < 1:
        raise ValueError("frame step must be >= 1")
    if last < first:
        raise ValueError("last frame must not precede the first frame")
    return list(range(first, last + 1, step))


def export(
    exporter: TachyonExporter,
    output,
    fmt: str,
    frames: Sequence[int],
    viewport=None,
    size: Sequence[int] = (1280, 720),
    fps: float = 10.0,
    background: Sequence[float] = (1.0, 1.0, 1.0),
    pipelines=None,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    """Render ``frames`` and write them as ``fmt`` (one of :data:`FORMATS`).

    For ``"png"`` only the first frame is rendered. For ``"sequence"`` the
    output is a directory that receives ``frame_00000.png`` etc. Returns the
    path written. Raises :class:`ExportCancelled` if ``progress`` returns False.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}")
    output = Path(output)
    width, height = int(size[0]), int(size[1])
    if fmt == "mp4" and (width % 2 or height % 2):
        raise ValueError("MP4 (H.264) needs an even image width and height")
    if fmt == "png":
        frames = list(frames)[:1]
    if not frames:
        raise ValueError("no frames to render")
    total = len(frames) + (1 if fmt in ("gif", "mp4") else 0)

    def report(done: int, message: str) -> None:
        if progress is not None and progress(done, total, message) is False:
            raise ExportCancelled()

    render_args = dict(viewport=viewport, size=(width, height), background=background, pipelines=pipelines)
    if fmt == "png":
        report(0, f"Frame {frames[0]}")
        exporter.render(output, frame=frames[0], **render_args)
        report(1, "Done")
        return output

    if fmt == "sequence":
        output.mkdir(parents=True, exist_ok=True)
        target_dir = output
    else:
        target_dir = Path(tempfile.mkdtemp(prefix="ovito_tachyon_frames_"))
    try:
        for i, frame in enumerate(frames):
            report(i, f"Frame {frame}  ·  {i + 1} / {len(frames)}")
            exporter.render(target_dir / f"frame_{i:05d}.png", frame=frame, **render_args)
        if fmt == "sequence":
            report(len(frames), "Done")
            return output
        report(len(frames), f"Encoding {fmt.upper()}")
        output.parent.mkdir(parents=True, exist_ok=True)
        encode(target_dir / "frame_%05d.png", output, fmt, fps)
        report(total, "Done")
        return output
    finally:
        if fmt != "sequence":
            shutil.rmtree(target_dir, ignore_errors=True)


def encode(pattern: Path, output: Path, fmt: str, fps: float) -> None:
    """Encode a numbered PNG sequence (ffmpeg ``%05d`` pattern) to GIF or MP4."""
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", f"{fps:g}", "-i", str(pattern)]
    if fmt == "mp4":
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
                "-movflags", "+faststart"]
    elif fmt == "gif":
        # Two-pass palette for clean colours; loop forever.
        cmd += ["-filter_complex", "[0:v]split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                "-loop", "0"]
    else:
        raise ValueError(f"cannot encode format {fmt!r}")
    cmd.append(str(output))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stdout}")
