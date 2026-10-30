"""Desktop application: open a trajectory, orbit the camera, export PNG/GIF/MP4 with Tachyon."""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

from . import __version__

APP_NAME = "OVITO-Tachyon"

SIZE_PRESETS = [
    ("720p", 1280, 720),
    ("1080p", 1920, 1080),
    ("1440p", 2560, 1440),
    ("4K", 3840, 2160),
    ("Square", 1080, 1080),
    ("Custom", 0, 0),
]

VIEWS = [
    ("Persp", "Perspective", (-1.0, -0.6, -0.5)),
    ("Ortho", "Ortho", (-1.0, -0.6, -0.5)),
    ("Top", "Ortho", (0.0, 0.0, -1.0)),
    ("Bottom", "Ortho", (0.0, 0.0, 1.0)),
    ("Front", "Ortho", (0.0, 1.0, 0.0)),
    ("Back", "Ortho", (0.0, -1.0, 0.0)),
    ("Left", "Ortho", (1.0, 0.0, 0.0)),
    ("Right", "Ortho", (-1.0, 0.0, 0.0)),
]

FORMATS = [("PNG", "png"), ("Sequence", "sequence"), ("GIF", "gif"), ("MP4", "mp4")]
FORMAT_SUFFIX = {"png": ".png", "sequence": "", "gif": ".gif", "mp4": ".mp4"}


class TypeStyle:
    """Per-type colour/radius overrides applied by a pipeline modifier, so they hold in every frame."""

    def __init__(self):
        self.colors: dict[int, tuple] = {}
        self.radii: dict[int, float] = {}

    def __call__(self, frame, data):
        if data.particles is None or data.particles.particle_types is None or not (self.colors or self.radii):
            return
        types = data.particles_.particle_types_
        for t in types.types:
            if t.id in self.colors:
                types.make_mutable(t).color = self.colors[t.id]
            if t.id in self.radii:
                types.make_mutable(t).radius = self.radii[t.id]


def scan_types(pipeline) -> dict[int, tuple]:
    """Collect particle types (id -> (name, color, radius)) from the first and last frame."""
    found: dict[int, tuple] = {}
    n = pipeline.source.num_frames
    for frame in sorted({0, max(n - 1, 0)}):
        data = pipeline.compute(frame)
        if data.particles is None or data.particles.particle_types is None:
            continue
        for t in data.particles.particle_types.types:
            found.setdefault(t.id, (t.name or f"Type {t.id}", tuple(t.color), float(t.radius)))
    return dict(sorted(found.items()))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        return selftest(argv[1] if len(argv) > 1 else "selftest_out")
    if argv[:1] == ["--version"]:
        print(f"{APP_NAME} {__version__}")
        return 0

    from PySide6 import QtCore, QtWidgets

    from .theme import stylesheet

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ovito-tachyon")
    app.setStyle("Fusion")
    icon_dir = Path(tempfile.gettempdir()) / "ovito-tachyon-icons"

    def apply_theme(*_):
        dark = app.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
        app.setStyleSheet(stylesheet(dark, icon_dir))

    apply_theme()
    app.styleHints().colorSchemeChanged.connect(apply_theme)

    window = MainWindow()
    window.show()
    if argv and not argv[0].startswith("-"):
        window.open_file(argv[0])
    return app.exec()


def selftest(out_dir: str) -> int:
    """Headless check of the bundled renderer and encoder (used by CI on the frozen app)."""
    from ovito.pipeline import Pipeline, PythonSource

    from .export import export, frame_list
    from .exporter import TachyonExporter

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def source(frame, data):
        data.create_cell([[10, 0, 0, 0], [0, 10, 0, 0], [0, 0, 10, 0]], pbc=(True, True, True))
        rng = np.random.default_rng(frame)
        particles = data.create_particles(count=50)
        particles.create_property("Position", data=rng.random((50, 3)) * 10)
        types = particles.create_property("Particle Type", data=rng.integers(1, 3, 50))
        types.add_type_id(1, particles, name="A").color = (1.0, 0.4, 0.4)
        types.add_type_id(2, particles, name="B").color = (0.4, 0.4, 1.0)

    pipeline = Pipeline(source=PythonSource(function=source))
    exporter = TachyonExporter(antialiasing_samples=2, ambient_occlusion_samples=4)
    for fmt, name in (("png", "frame.png"), ("gif", "anim.gif"), ("mp4", "anim.mp4")):
        path = export(exporter, out / name, fmt, frame_list(0, 3), size=(160, 120), pipelines=[pipeline])
        print(f"{fmt}: {path} ({path.stat().st_size} bytes)")
    image = exporter.render(None, size=(160, 120), pipelines=[pipeline])
    if (image > 250).all():
        print("selftest: rendered image is blank")
        return 1
    return 0


# --------------------------------------------------------------------------- GUI
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402


def _section(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName("Section")
    return label


def _spin(lo, hi, value, double=False, step=None):
    spin = QtWidgets.QDoubleSpinBox() if double else QtWidgets.QSpinBox()
    spin.setRange(lo, hi)
    spin.setValue(value)
    spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    if step is not None:
        spin.setSingleStep(step)
    return spin


class ToggleGroup(QtWidgets.QWidget):
    """shadcn-style segmented control."""

    def __init__(self, labels, columns=None, exclusive=True):
        super().__init__()
        self.setObjectName("ToggleGroup")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(3, 3, 3, 3)
        grid.setSpacing(2)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(exclusive)
        columns = columns or len(labels)
        self.buttons = []
        for i, label in enumerate(labels):
            b = QtWidgets.QPushButton(label)
            b.setObjectName("Toggle")
            b.setCheckable(True)
            self.group.addButton(b, i)
            grid.addWidget(b, i // columns, i % columns)
            self.buttons.append(b)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        import ovito
        import ovito.gui
        from ovito.vis import Viewport

        self.setWindowTitle(APP_NAME)
        self.resize(1440, 880)
        self.setAcceptDrops(True)
        self.settings = QtCore.QSettings()
        self.scene = ovito.scene
        self.pipeline = None
        self.input_path: Path | None = None
        self.type_style = TypeStyle()
        self.background = (1.0, 1.0, 1.0)

        self.vp = Viewport(type=Viewport.Type.Perspective, camera_dir=VIEWS[0][2])
        self.vp.preview_mode = True
        self.vp_window = ovito.gui.create_qwidget(self.vp, parent=self)

        self.play_timer = QtCore.QTimer(self)
        self.play_timer.timeout.connect(self._advance_frame)

        self._build()
        self._format_changed()
        self._apply_size()
        self._set_loaded(False)

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(0)
        self.stack = QtWidgets.QStackedWidget()
        empty = QtWidgets.QWidget()
        e = QtWidgets.QVBoxLayout(empty)
        open_big = QtWidgets.QPushButton("Open trajectory")
        open_big.setObjectName("Primary")
        open_big.setMinimumWidth(180)
        open_big.clicked.connect(self.choose_file)
        e.addStretch(1)
        e.addWidget(open_big, 0, QtCore.Qt.AlignCenter)
        e.addStretch(1)
        self.stack.addWidget(empty)
        self.stack.addWidget(self.vp_window.widget)
        left.addWidget(self.stack, 1)
        left.addWidget(self._bottom_bar())
        h.addLayout(left, 1)
        h.addWidget(self._sidebar())
        self.setCentralWidget(root)

        menu = self.menuBar().addMenu("File")
        menu.addAction("Open…", QtGui.QKeySequence.Open, self.choose_file)
        menu.addAction("Export", QtGui.QKeySequence("Ctrl+E"), self.run_export)
        menu.addSeparator()
        menu.addAction("Quit", QtGui.QKeySequence.Quit, self.close)

    def _bottom_bar(self):
        bar = QtWidgets.QWidget()
        bar.setObjectName("BottomBar")
        bar.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        self.play_button = QtWidgets.QPushButton("▶")
        self.play_button.setObjectName("Icon")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._toggle_play)
        self.frame_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.frame_spin = _spin(0, 0, 0)
        self.frame_spin.setFixedWidth(110)
        self.frame_spin.setAlignment(QtCore.Qt.AlignRight)
        self.frame_slider.valueChanged.connect(self.frame_spin.setValue)
        self.frame_spin.valueChanged.connect(self.frame_slider.setValue)
        self.frame_slider.valueChanged.connect(self._set_frame)
        self.step_label = QtWidgets.QLabel()
        self.step_label.setObjectName("Muted")
        self.step_label.setMinimumWidth(110)
        lay.addWidget(self.play_button)
        lay.addWidget(self.frame_slider, 1)
        lay.addWidget(self.frame_spin)
        lay.addWidget(self.step_label)
        return bar

    def _sidebar(self):
        body = QtWidgets.QWidget()
        body.setObjectName("SidebarBody")
        v = QtWidgets.QVBoxLayout(body)
        v.setContentsMargins(16, 12, 16, 16)
        v.setSpacing(8)

        self.file_button = QtWidgets.QPushButton("Open…")
        self.file_button.clicked.connect(self.choose_file)
        v.addWidget(self.file_button)

        v.addWidget(_section("View"))
        self.view_group = ToggleGroup([label for label, _, _ in VIEWS], columns=4)
        self.view_group.buttons[0].setChecked(True)
        self.view_group.group.idClicked.connect(lambda i: self.set_view(*VIEWS[i][1:]))
        fit = QtWidgets.QPushButton("Fit")
        fit.clicked.connect(self.zoom_all)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.view_group, 1)
        row.addWidget(fit, 0, QtCore.Qt.AlignTop)
        v.addLayout(row)

        v.addWidget(_section("Atoms"))
        self.types_box = QtWidgets.QVBoxLayout()
        self.types_box.setSpacing(6)
        v.addLayout(self.types_box)
        scene_form = QtWidgets.QFormLayout()
        self.cell_check = QtWidgets.QCheckBox("Cell")
        self.cell_check.setChecked(True)
        self.cell_check.toggled.connect(self._apply_cell_visibility)
        self.bg_button = QtWidgets.QPushButton()
        self.bg_button.setObjectName("Swatch")
        self._paint_swatch(self.bg_button, self.background)
        self.bg_button.clicked.connect(self._choose_background)
        bg_row = QtWidgets.QHBoxLayout()
        bg_row.addWidget(self.cell_check)
        bg_row.addStretch(1)
        bg_row.addWidget(QtWidgets.QLabel("Background"))
        bg_row.addWidget(self.bg_button)
        scene_form.addRow(bg_row)
        v.addLayout(scene_form)

        v.addWidget(_section("Render"))
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        self.aa_spin = _spin(0, 64, 12)
        self.ao_check = QtWidgets.QCheckBox()
        self.ao_check.setChecked(True)
        self.ao_spin = _spin(1, 128, 12)
        self.ao_check.toggled.connect(self.ao_spin.setEnabled)
        ao_row = QtWidgets.QHBoxLayout()
        ao_row.addWidget(self.ao_check)
        ao_row.addWidget(self.ao_spin, 1)
        self.shadow_check = QtWidgets.QCheckBox()
        self.shadow_check.setChecked(True)
        self.brightness_spin = _spin(0.0, 1.0, 0.3, double=True, step=0.05)
        form.addRow("Antialiasing", self.aa_spin)
        form.addRow("Ambient occlusion", ao_row)
        form.addRow("Shadows", self.shadow_check)
        form.addRow("Brightness", self.brightness_spin)
        v.addLayout(form)

        v.addWidget(_section("Output"))
        self.format_group = ToggleGroup([label for label, _ in FORMATS])
        self.format_group.buttons[3].setChecked(True)
        self.format_group.group.idClicked.connect(self._format_changed)
        v.addWidget(self.format_group)

        out = QtWidgets.QFormLayout()
        out.setLabelAlignment(QtCore.Qt.AlignLeft)
        self.size_combo = QtWidgets.QComboBox()
        for label, w, hgt in SIZE_PRESETS:
            self.size_combo.addItem(label, (w, hgt))
        self.size_combo.currentIndexChanged.connect(self._preset_selected)
        self.width_spin = _spin(16, 8192, 1280, step=2)
        self.height_spin = _spin(16, 8192, 720, step=2)
        for spin in (self.width_spin, self.height_spin):
            spin.editingFinished.connect(self._apply_size)
        size_row = QtWidgets.QHBoxLayout()
        size_row.addWidget(self.size_combo, 1)
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QtWidgets.QLabel("×"))
        size_row.addWidget(self.height_spin)
        out.addRow("Size", size_row)

        self.first_spin = _spin(0, 0, 0)
        self.last_spin = _spin(0, 0, 0)
        self.stride_spin = _spin(1, 100000, 1)
        self.stride_spin.setPrefix("every ")
        frames_row = QtWidgets.QHBoxLayout()
        frames_row.addWidget(self.first_spin)
        dash = QtWidgets.QLabel("–")
        dash.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        frames_row.addWidget(dash)
        frames_row.addWidget(self.last_spin)
        frames_row.addWidget(self.stride_spin)
        self.frames_label = QtWidgets.QLabel("Frames")
        out.addRow(self.frames_label, frames_row)
        self.fps_spin = _spin(0.5, 120.0, 20.0, double=True)
        self.fps_spin.setDecimals(1)
        self.fps_spin.setSuffix(" fps")
        self.fps_label = QtWidgets.QLabel("Rate")
        out.addRow(self.fps_label, self.fps_spin)

        self.out_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("…")
        browse.setObjectName("Icon")
        browse.clicked.connect(self._choose_output)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.out_edit, 1)
        path_row.addWidget(browse)
        out.addRow("Save to", path_row)
        v.addLayout(out)

        self.preview_button = QtWidgets.QPushButton("Preview")
        self.preview_button.clicked.connect(self.render_preview)
        self.export_button = QtWidgets.QPushButton("Export")
        self.export_button.setObjectName("Primary")
        self.export_button.clicked.connect(self.run_export)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.export_button, 1)
        v.addSpacing(6)
        v.addLayout(buttons)
        v.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("Sidebar")
        scroll.setFixedWidth(380)
        return scroll

    # ------------------------------------------------------------ file
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.open_file(urls[0].toLocalFile())

    def choose_file(self):
        start = self.settings.value("last_dir", str(Path.home()))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", start)
        if path:
            self.open_file(path)

    def open_file(self, path):
        from ovito.io import import_file
        from ovito.modifiers import PythonModifier

        path = Path(path)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            try:
                pipeline = import_file(str(path))
            except Exception as exc:
                QtWidgets.QApplication.restoreOverrideCursor()
                QtWidgets.QMessageBox.critical(self, APP_NAME, f"{path.name}\n\n{exc}")
                return
            if self.pipeline is not None:
                self.pipeline.remove_from_scene()
            self.type_style = TypeStyle()
            pipeline.modifiers.append(PythonModifier(function=self.type_style))
            pipeline.add_to_scene()
            self.pipeline = pipeline
            self.input_path = path
            self.settings.setValue("last_dir", str(path.parent))

            last = pipeline.source.num_frames - 1
            for spin in (self.frame_spin, self.first_spin, self.last_spin):
                spin.setRange(0, last)
            self.frame_spin.setSuffix(f" / {last}")
            self.frame_slider.setRange(0, last)
            self.first_spin.setValue(0)
            self.last_spin.setValue(last)
            self.frame_slider.setValue(0)
            self._set_frame(0)
            self._populate_types(scan_types(pipeline))
            self._apply_cell_visibility(self.cell_check.isChecked())
            self.file_button.setText(path.name)
            self.file_button.setToolTip(str(path))
            self.setWindowTitle(f"{path.name} — {APP_NAME}")
            self.out_edit.clear()
            self._suggest_output()
            self._set_loaded(True)
            self.zoom_all()
            # Fit again once the viewport has been laid out and the first frame evaluated.
            QtCore.QTimer.singleShot(300, self.zoom_all)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _set_loaded(self, on: bool):
        self.stack.setCurrentIndex(1 if on else 0)
        for w in (self.preview_button, self.export_button, self.frame_slider, self.frame_spin, self.play_button):
            w.setEnabled(on)

    # ------------------------------------------------------------ frames / view
    def _set_frame(self, frame: int):
        if self.pipeline is None:
            return
        self.scene.anim.current_frame = int(frame)
        timestep = self.pipeline.compute(int(frame)).attributes.get("Timestep")
        self.step_label.setText("" if timestep is None else f"step {timestep}")

    def _toggle_play(self, on: bool):
        self.play_button.setText("❚❚" if on else "▶")
        if on:
            self.play_timer.start(int(1000 / max(self.fps_spin.value(), 1)))
        else:
            self.play_timer.stop()

    def _advance_frame(self):
        nxt = self.frame_slider.value() + self.stride_spin.value()
        self.frame_slider.setValue(nxt if nxt <= self.frame_slider.maximum() else 0)

    def set_view(self, kind: str, direction):
        from ovito.vis import Viewport

        self.vp.type = getattr(Viewport.Type, kind)
        self.vp.camera_dir = direction
        self.vp.camera_up = (0.0, 0.0, 0.0)
        self.zoom_all()

    def zoom_all(self):
        self.vp.zoom_all(size=self._output_size())

    # ------------------------------------------------------------ appearance
    def _populate_types(self, types: dict):
        while self.types_box.count():
            item = self.types_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        for tid, (name, color, radius) in types.items():
            row = QtWidgets.QHBoxLayout()
            swatch = QtWidgets.QPushButton()
            swatch.setObjectName("Swatch")
            self._paint_swatch(swatch, color)
            swatch.clicked.connect(lambda _=False, t=tid, b=swatch: self._choose_type_color(t, b))
            radius_spin = _spin(0.0, 10.0, radius, double=True, step=0.1)
            radius_spin.setSpecialValueText("auto")
            radius_spin.setPrefix("r ")
            radius_spin.setFixedWidth(90)
            radius_spin.valueChanged.connect(lambda val, t=tid: self._set_type_radius(t, val))
            row.addWidget(swatch)
            row.addWidget(QtWidgets.QLabel(name), 1)
            row.addWidget(radius_spin)
            self.types_box.addLayout(row)

    @staticmethod
    def _paint_swatch(button, color):
        r, g, b = (int(round(255 * c)) for c in color[:3])
        button.setStyleSheet(f"background-color: rgb({r},{g},{b});")
        button.setProperty("rgb", (r / 255, g / 255, b / 255))

    def _pick_color(self, button):
        r, g, b = button.property("rgb")
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor.fromRgbF(r, g, b), self)
        if not col.isValid():
            return None
        rgb = (col.redF(), col.greenF(), col.blueF())
        self._paint_swatch(button, rgb)
        return rgb

    def _choose_type_color(self, tid, button):
        rgb = self._pick_color(button)
        if rgb:
            self.type_style.colors[tid] = rgb
            self._refresh_pipeline()

    def _set_type_radius(self, tid, value):
        if value > 0:
            self.type_style.radii[tid] = value
        else:
            self.type_style.radii.pop(tid, None)
        self._refresh_pipeline()

    def _refresh_pipeline(self):
        if self.pipeline is not None:
            self.pipeline.modifiers[-1].notify_object_changed()

    def _apply_cell_visibility(self, on: bool):
        if self.pipeline is not None and self.pipeline.source.data.cell is not None:
            self.pipeline.source.data.cell_.vis.enabled = on

    def _choose_background(self):
        rgb = self._pick_color(self.bg_button)
        if rgb:
            self.background = rgb
            self.scene.render_settings.background_color = rgb

    # ------------------------------------------------------------ output
    def _fmt(self) -> str:
        return FORMATS[self.format_group.group.checkedId()][1]

    def _format_changed(self, *_):
        fmt = self._fmt()
        animated = fmt in ("gif", "mp4")
        for w in (self.frames_label, self.first_spin, self.last_spin, self.stride_spin):
            w.setVisible(fmt != "png")
        self.fps_label.setVisible(animated)
        self.fps_spin.setVisible(animated)
        self._suggest_output()

    def _preset_selected(self, index: int):
        w, h = self.size_combo.itemData(index)
        if w:
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
            self._apply_size()

    def _output_size(self):
        return self.width_spin.value(), self.height_spin.value()

    def _apply_size(self):
        # Even sizes keep every format (H.264 included) valid.
        for spin in (self.width_spin, self.height_spin):
            if spin.value() % 2:
                spin.setValue(spin.value() + 1)
        w, h = self._output_size()
        self.scene.render_settings.output_image_width = w
        self.scene.render_settings.output_image_height = h
        match = next((i for i, (_, pw, ph) in enumerate(SIZE_PRESETS) if (pw, ph) == (w, h)), len(SIZE_PRESETS) - 1)
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentIndex(match)
        self.size_combo.blockSignals(False)

    def _frames(self):
        from .export import frame_list

        first = self.first_spin.value()
        return frame_list(first, max(self.last_spin.value(), first), self.stride_spin.value())

    def _suggest_output(self):
        if self.input_path is None:
            return
        fmt = self._fmt()
        current = self.out_edit.text().strip()
        folder = Path(current).parent if current else self.input_path.parent
        stem = self.input_path.stem + ("_frames" if fmt == "sequence" else "")
        self.out_edit.setText(str(folder / (stem + FORMAT_SUFFIX[fmt])))

    def _choose_output(self):
        fmt = self._fmt()
        current = self.out_edit.text() or str(Path.home())
        if fmt == "sequence":
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Save to", current)
        else:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save to", current, f"*{FORMAT_SUFFIX[fmt]}")
            if path and not path.lower().endswith(FORMAT_SUFFIX[fmt]):
                path += FORMAT_SUFFIX[fmt]
        if path:
            self.out_edit.setText(path)

    def _make_exporter(self):
        from .exporter import TachyonExporter
        from .scene import Material

        return TachyonExporter(
            antialiasing=self.aa_spin.value() > 0,
            antialiasing_samples=self.aa_spin.value(),
            ambient_occlusion=self.ao_check.isChecked(),
            ambient_occlusion_samples=self.ao_spin.value(),
            shadows=self.shadow_check.isChecked(),
            material=Material(ambient=self.brightness_spin.value()),
        )

    def render_preview(self):
        if self.pipeline is None:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            image = self._make_exporter().render(None, viewport=self.vp, size=self._output_size(),
                                                 frame=self.frame_slider.value(), background=self.background,
                                                 pipelines=[self.pipeline])
        except Exception:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._show_error()
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        PreviewDialog(image, self).exec()

    def run_export(self):
        from .export import ExportCancelled, export

        if self.pipeline is None:
            return
        fmt = self._fmt()
        out = self.out_edit.text().strip()
        if not out:
            self._choose_output()
            out = self.out_edit.text().strip()
            if not out:
                return
        if Path(out).exists() and fmt != "sequence":
            answer = QtWidgets.QMessageBox.question(self, APP_NAME, f"Replace {Path(out).name}?")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        frames = [self.frame_slider.value()] if fmt == "png" else self._frames()

        self.play_button.setChecked(False)
        dialog = QtWidgets.QProgressDialog("", "Cancel", 0, len(frames), self)
        dialog.setWindowTitle("Export")
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setMinimumWidth(420)
        dialog.setValue(0)

        def progress(done, total, message):
            dialog.setMaximum(total)
            dialog.setValue(done)
            dialog.setLabelText(message)
            QtWidgets.QApplication.processEvents()
            return not dialog.wasCanceled()

        try:
            path = export(self._make_exporter(), out, fmt, frames, viewport=self.vp, size=self._output_size(),
                          fps=self.fps_spin.value(), background=self.background,
                          pipelines=[self.pipeline], progress=progress)
        except ExportCancelled:
            return
        except Exception:
            self._show_error()
            return
        finally:
            dialog.close()
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(str(path))
        reveal = box.addButton("Show in folder", QtWidgets.QMessageBox.ActionRole)
        box.addButton(QtWidgets.QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is reveal:
            target = path if path.is_dir() else path.parent
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))

    def _show_error(self):
        QtWidgets.QMessageBox.critical(self, APP_NAME, traceback.format_exc(limit=3))


class PreviewDialog(QtWidgets.QDialog):
    def __init__(self, image: np.ndarray, parent=None):
        super().__init__(parent)
        self.image = np.ascontiguousarray(image)
        h, w, _ = self.image.shape
        self.setWindowTitle(f"{w} × {h}")
        qimg = QtGui.QImage(self.image.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
        screen = self.screen().availableGeometry()
        label = QtWidgets.QLabel()
        label.setPixmap(QtGui.QPixmap.fromImage(qimg).scaled(
            min(w, int(screen.width() * 0.8)), min(h, int(screen.height() * 0.8)),
            QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        save = QtWidgets.QPushButton("Save…")
        save.clicked.connect(self._save)
        close = QtWidgets.QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save)
        buttons.addWidget(close)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(label)
        lay.addLayout(buttons)

    def _save(self):
        from .image import write_png

        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save", str(Path.home() / "render.png"), "*.png")
        if path:
            write_png(path if path.lower().endswith(".png") else path + ".png", self.image)


if __name__ == "__main__":
    sys.exit(main())
