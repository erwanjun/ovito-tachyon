"""Desktop application: open a trajectory, orbit the camera, export PNG/GIF/MP4 with Tachyon."""

from __future__ import annotations

import functools
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

from . import __version__
from .i18n import LANGUAGES, language, set_language, tr

APP_NAME = "OVITO-Tachyon"
ASSETS = Path(__file__).resolve().parent / "assets"

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

# OVITO's default type colors, a few element colors and neutrals.
PALETTE = ["#ff6666", "#6666ff", "#ffff00", "#ff66ff", "#66ff33", "#ff9933", "#33cccc", "#996633",
           "#909090", "#ff0d0d", "#3050f8", "#f0c8a0", "#80d1e3", "#ffffff", "#737373", "#0a0a0a"]

FORMATS = [("PNG", "png"), ("Sequence", "sequence"), ("GIF", "gif"), ("MP4", "mp4")]
FORMAT_SUFFIX = {"png": ".png", "sequence": "", "gif": ".gif", "mp4": ".mp4"}


class TypeStyle:
    """Per-type colour/radius/visibility overrides applied by a pipeline modifier, so they hold in every frame."""

    def __init__(self):
        self.colors: dict[int, tuple] = {}
        self.radii: dict[int, float] = {}
        self.hidden: set[int] = set()

    def __call__(self, frame, data):
        if data.particles is None or data.particles.particle_types is None:
            return
        if self.hidden:
            ids = np.asarray(data.particles.particle_types)
            data.particles_.delete_elements(np.isin(ids, list(self.hidden)))
        if not (self.colors or self.radii):
            return
        types = data.particles_.particle_types_
        for t in types.types:
            if t.id in self.colors or t.id in self.radii:
                t = types.make_mutable(t)
                t.color = self.colors.get(t.id, t.color)
                t.radius = self.radii.get(t.id, t.radius)


def scan_types(pipeline) -> dict[int, tuple]:
    """Collect particle types (id -> (name, color, radius)) from the first and last frame."""
    found: dict[int, tuple] = {}
    n = pipeline.source.num_frames
    for frame in sorted({0, max(n - 1, 0)}):
        data = pipeline.compute(frame)
        if data.particles is None or data.particles.particle_types is None:
            continue
        for t in data.particles.particle_types.types:
            found.setdefault(t.id, (t.name, tuple(t.color), float(t.radius)))
    return dict(sorted(found.items()))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        return selftest(argv[1] if len(argv) > 1 else "selftest_out")
    if argv[:1] == ["--version"]:
        print(f"{APP_NAME} {__version__}")
        return 0

    from PySide6 import QtCore, QtGui, QtWidgets

    from .theme import stylesheet

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ovito-tachyon")
    app.setStyle("Fusion")
    app.setWindowIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(app_icon_image(512))))
    icon_dir = Path(tempfile.gettempdir()) / "ovito-tachyon-icons"

    settings = QtCore.QSettings()
    default = "zh" if QtCore.QLocale.system().language() == QtCore.QLocale.Chinese else "en"
    set_language(str(settings.value("language", default)))
    _install_qt_translator(app)

    window = MainWindow()

    def apply_theme(*_):
        dark = app.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
        app.setStyleSheet(stylesheet(dark, icon_dir))
        window.set_dark(dark)

    apply_theme()
    app.styleHints().colorSchemeChanged.connect(apply_theme)
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

    # Also log to a file: windowed builds have no console to print to.
    with open(out / "selftest.log", "w", encoding="utf-8") as log:
        def report(line):
            print(line)
            log.write(line + "\n")
            log.flush()

        try:
            pipeline = Pipeline(source=PythonSource(function=source))
            exporter = TachyonExporter(antialiasing_samples=2, ambient_occlusion_samples=4)
            for fmt, name in (("png", "frame.png"), ("gif", "anim.gif"), ("mp4", "anim.mp4")):
                path = export(exporter, out / name, fmt, frame_list(0, 3), size=(160, 120), pipelines=[pipeline])
                report(f"{fmt}: {path} ({path.stat().st_size} bytes)")
            image = exporter.render(None, size=(160, 120), pipelines=[pipeline])
        except Exception:
            report(traceback.format_exc())
            return 1
        if (image > 250).all():
            report("selftest: rendered image is blank")
            return 1
        report("selftest: ok")
    return 0


# --------------------------------------------------------------------------- GUI
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets  # noqa: E402

_qt_translator = None


def _install_qt_translator(app) -> None:
    """Load Qt's own translations (standard buttons, colour and file dialogs) for the current language."""
    global _qt_translator
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if language() == "zh":
        translator = QtCore.QTranslator(app)
        path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath)
        if translator.load(QtCore.QLocale(QtCore.QLocale.Chinese, QtCore.QLocale.China), "qtbase", "_", path):
            app.installTranslator(translator)
            _qt_translator = translator


def _svg_pixmap(name: str, color: str, height: int, ratio: float = 2.0) -> QtGui.QPixmap:
    svg = (ASSETS / f"{name}.svg").read_text(encoding="utf-8").replace('fill="#000000"', f'fill="{color}"')
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))
    size = renderer.defaultSize()
    w = round(height * size.width() / size.height())
    pixmap = QtGui.QPixmap(round(w * ratio), round(height * ratio))
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def app_icon_image(size: int) -> QtGui.QImage:
    """The application icon: white logo on a dark rounded tile, laid out on the macOS icon grid."""
    tile, radius, glyph = size * 824 / 1024, size * 185 / 1024, size * 520 / 1024
    svg = (ASSETS / "logo.svg").read_text(encoding="utf-8").replace('fill="#000000"', 'fill="#fafafa"')
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))
    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor("#0a0a0a"))
    offset = (size - tile) / 2
    painter.drawRoundedRect(QtCore.QRectF(offset, offset, tile, tile), radius, radius)
    g = (size - glyph) / 2
    renderer.render(painter, QtCore.QRectF(g, g, glyph, glyph))
    painter.end()
    return image


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

    def __init__(self, count, columns=None):
        super().__init__()
        self.setObjectName("ToggleGroup")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(3, 3, 3, 3)
        grid.setSpacing(2)
        self.group = QtWidgets.QButtonGroup(self)
        columns = columns or count
        self.buttons = []
        for i in range(count):
            b = QtWidgets.QPushButton()
            b.setObjectName("Toggle")
            b.setCheckable(True)
            self.group.addButton(b, i)
            grid.addWidget(b, i // columns, i % columns)
            self.buttons.append(b)


def color_hex(rgb) -> str:
    return "#" + "".join(f"{round(255 * min(max(c, 0.0), 1.0)):02x}" for c in rgb[:3])


def parse_color(text: str):
    """``#rgb``, ``#rrggbb`` (``#`` optional), or ``r, g, b`` in 0-255 (in 0-1 when all are <= 1). None if invalid."""
    text = text.strip()
    digits = text.lstrip("#")
    if len(digits) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in digits):
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))
    parts = text.replace(",", " ").split()
    if len(parts) == 3:
        try:
            values = [float(p) for p in parts]
        except ValueError:
            return None
        scale = 1.0 if all(v <= 1.0 for v in values) else 255.0
        if all(0 <= v <= scale for v in values):
            return tuple(v / scale for v in values)
    return None


def _exclusive(method):
    """OVITO evaluations (compute, zoom_all, rendering) spin a nested event loop, and starting another one from an
    event handled inside it crashes OVITO. Decorated methods never overlap: a call made while one runs is retried."""

    @functools.wraps(method)
    def wrapper(self, *args):
        if self._busy:
            QtCore.QTimer.singleShot(50, lambda: wrapper(self, *args))
            return None
        self._busy = True
        try:
            return method(self, *args)
        finally:
            self._busy = False

    return wrapper


class ColorPopup(QtWidgets.QFrame):
    """Popover under a swatch: type a color code, or click a palette swatch. Valid input applies as you type."""

    picked = QtCore.Signal(tuple)

    def __init__(self, rgb, palette, parent):
        super().__init__(parent, QtCore.Qt.Popup)
        self.setObjectName("Popover")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.rgb = tuple(rgb)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        self.code = QtWidgets.QLineEdit(color_hex(rgb))
        self.code.setPlaceholderText("#rrggbb")
        self.code.textEdited.connect(self._typed)
        self.code.returnPressed.connect(self.close)
        v.addWidget(self.code)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        for i, code in enumerate(palette):
            swatch = QtWidgets.QPushButton()
            swatch.setObjectName("Swatch")
            swatch.setToolTip(code)
            swatch.setStyleSheet(f"background-color: {code};")
            swatch.clicked.connect(lambda _=False, c=code: self._choose(parse_color(c)))
            grid.addWidget(swatch, i // 8, i % 8)
        v.addLayout(grid)
        more = QtWidgets.QPushButton(tr("More…"))
        more.clicked.connect(self._system_dialog)
        v.addWidget(more)

    def show_below(self, widget):
        self.adjustSize()
        pos = widget.mapToGlobal(QtCore.QPoint(widget.width() - self.width(), widget.height() + 4))
        screen = widget.screen().availableGeometry()
        pos.setX(max(screen.left(), min(pos.x(), screen.right() - self.width())))
        if pos.y() + self.height() > screen.bottom():
            pos.setY(widget.mapToGlobal(QtCore.QPoint(0, -self.height() - 4)).y())
        self.move(pos)
        self.show()
        self.code.setFocus()
        self.code.selectAll()

    def _typed(self, text):
        rgb = parse_color(text)
        if rgb:
            self.rgb = rgb
            self.picked.emit(rgb)

    def _choose(self, rgb):
        self.picked.emit(rgb)
        self.close()

    def _system_dialog(self):
        start = QtGui.QColor.fromRgbF(*self.rgb)
        parent = self.parentWidget()
        self.close()
        color = QtWidgets.QColorDialog.getColor(start, parent)
        if color.isValid():
            self.picked.emit((color.redF(), color.greenF(), color.blueF()))


class PanFilter(QtCore.QObject):
    """In pan mode, turns left-drags in the OVITO viewport into middle-drags, which OVITO treats as panning."""

    _MOUSE = (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseMove,
              QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick)

    def __init__(self, parent):
        super().__init__(parent)
        self.enabled = False
        self.windows = set()

    def attach(self, window):
        if window is not None and window not in self.windows:
            window.installEventFilter(self)
            self.windows.add(window)

    def eventFilter(self, obj, event):
        if not self.enabled or event.type() not in self._MOUSE:
            return False
        left, middle = QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton
        if event.button() != left and not event.buttons() & left:
            return False
        button = middle if event.button() == left else event.button()
        buttons = (event.buttons() & ~left) | middle if event.buttons() & left else event.buttons()
        QtCore.QCoreApplication.sendEvent(obj, QtGui.QMouseEvent(
            event.type(), event.position(), event.globalPosition(), button, buttons, event.modifiers()))
        return True


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
        self.types: dict[int, tuple] = {}
        self.background = (1.0, 1.0, 1.0)
        self.dark = False
        self._texts: list[tuple] = []

        self.vp = Viewport(type=Viewport.Type.Perspective, camera_dir=VIEWS[0][2])
        self.vp.preview_mode = True
        self.vp_window = ovito.gui.create_qwidget(self.vp, parent=self)

        self.play_timer = QtCore.QTimer(self)
        self.play_timer.timeout.connect(self._advance_frame)
        # Frame changes only set the animation frame; the timestep label follows once the slider settles.
        self._busy = False
        self.step_timer = QtCore.QTimer(self)
        self.step_timer.setSingleShot(True)
        self.step_timer.setInterval(120)
        self.step_timer.timeout.connect(self._update_step)
        self.pan_filter = PanFilter(self)

        self._build()
        self._format_changed()
        self._apply_size()
        self._set_loaded(False)

    # ------------------------------------------------------------ i18n
    def _bind(self, setter, key, **kwargs):
        """Set a translated text now and again whenever the language changes."""
        self._texts.append((setter, key, kwargs))
        setter(tr(key, **kwargs))

    def set_language(self, lang: str):
        set_language(lang)
        self.settings.setValue("language", lang)
        _install_qt_translator(QtWidgets.QApplication.instance())
        for setter, key, kwargs in self._texts:
            setter(tr(key, **kwargs))
        for action in self.language_actions.actions():
            action.setChecked(action.data() == lang)
        self._populate_types(self.types)
        self._set_frame(self.frame_slider.value())

    def set_dark(self, dark: bool):
        self.dark = dark
        color = "#fafafa" if dark else "#0a0a0a"
        self.logo_label.setPixmap(_svg_pixmap("logo", color, 72))
        self.wordmark_label.setPixmap(_svg_pixmap("wordmark", color, 30))

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(0)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._empty_state())
        self.stack.addWidget(self.vp_window.widget)
        left.addWidget(self.stack, 1)
        left.addWidget(self._bottom_bar())
        h.addLayout(left, 1)
        h.addWidget(self._sidebar())
        self.setCentralWidget(root)

        menu = self.menuBar().addMenu("")
        self._bind(menu.setTitle, "File")
        for key, shortcut, slot in (("Open…", QtGui.QKeySequence.Open, self.choose_file),
                                    ("Export", QtGui.QKeySequence("Ctrl+E"), lambda: self.run_export())):
            action = menu.addAction("", shortcut, slot)
            self._bind(action.setText, key)
        menu.addSeparator()
        quit_action = menu.addAction("", QtGui.QKeySequence.Quit, self.close)
        self._bind(quit_action.setText, "Quit")

        lang_menu = self.menuBar().addMenu("Language / 语言")
        self.language_actions = QtGui.QActionGroup(self)
        for code, name in LANGUAGES.items():
            action = lang_menu.addAction(name)
            action.setCheckable(True)
            action.setData(code)
            action.setChecked(code == language())
            action.triggered.connect(lambda _=False, c=code: self.set_language(c))
            self.language_actions.addAction(action)

    def _empty_state(self):
        empty = QtWidgets.QWidget()
        e = QtWidgets.QVBoxLayout(empty)
        e.setSpacing(18)
        self.logo_label = QtWidgets.QLabel()
        self.wordmark_label = QtWidgets.QLabel()
        open_big = QtWidgets.QPushButton()
        self._bind(open_big.setText, "Open trajectory")
        open_big.setObjectName("Primary")
        open_big.setMinimumWidth(180)
        open_big.clicked.connect(self.choose_file)
        e.addStretch(1)
        e.addWidget(self.logo_label, 0, QtCore.Qt.AlignCenter)
        e.addWidget(self.wordmark_label, 0, QtCore.Qt.AlignCenter)
        e.addSpacing(10)
        e.addWidget(open_big, 0, QtCore.Qt.AlignCenter)
        e.addStretch(1)
        return empty

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
        self.step_label.setMinimumWidth(130)
        lay.addWidget(self.play_button)
        lay.addWidget(self.frame_slider, 1)
        lay.addWidget(self.frame_spin)
        lay.addWidget(self.step_label)
        return bar

    def _label(self, key):
        label = QtWidgets.QLabel()
        self._bind(label.setText, key)
        return label

    def _sidebar(self):
        body = QtWidgets.QWidget()
        body.setObjectName("SidebarBody")
        v = QtWidgets.QVBoxLayout(body)
        v.setContentsMargins(16, 12, 16, 16)
        v.setSpacing(8)

        self.file_button = QtWidgets.QPushButton()
        self._file_text = ("Open…", {})
        self._bind(self._set_file_text, "Open…")
        self.file_button.clicked.connect(self.choose_file)
        v.addWidget(self.file_button)

        section = _section("")
        self._bind(section.setText, "View")
        v.addWidget(section)
        self.view_group = ToggleGroup(len(VIEWS), columns=4)
        for button, (key, _, _) in zip(self.view_group.buttons, VIEWS):
            self._bind(button.setText, key)
        self.view_group.buttons[0].setChecked(True)
        self.view_group.group.idClicked.connect(lambda i: self.set_view(*VIEWS[i][1:]))
        fit = QtWidgets.QPushButton()
        self._bind(fit.setText, "Fit")
        fit.clicked.connect(lambda: self.zoom_all())
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.view_group, 1)
        row.addWidget(fit, 0, QtCore.Qt.AlignTop)
        v.addLayout(row)
        self.drag_group = ToggleGroup(2)
        for button, key in zip(self.drag_group.buttons, ("Rotate", "Pan")):
            self._bind(button.setText, key)
        self.drag_group.buttons[0].setChecked(True)
        self.drag_group.group.idClicked.connect(self._set_drag_mode)
        v.addWidget(self.drag_group)

        section = _section("")
        self._bind(section.setText, "Atoms")
        import_button = QtWidgets.QPushButton()
        import_button.setObjectName("Link")
        self._bind(import_button.setText, "From .ovito…")
        import_button.clicked.connect(lambda: self.import_ovito_types())
        header = QtWidgets.QHBoxLayout()
        header.addWidget(section)
        header.addStretch(1)
        header.addWidget(import_button, 0, QtCore.Qt.AlignBottom)
        v.addLayout(header)
        self.types_box = QtWidgets.QVBoxLayout()
        self.types_box.setSpacing(6)
        v.addLayout(self.types_box)
        self.cell_check = QtWidgets.QCheckBox()
        self._bind(self.cell_check.setText, "Box")
        self.cell_check.setChecked(True)
        self.cell_check.toggled.connect(self._apply_cell_visibility)
        self.bg_button = QtWidgets.QPushButton()
        self.bg_button.setObjectName("Swatch")
        self._paint_swatch(self.bg_button, self.background)
        self.bg_button.clicked.connect(self._choose_background)
        bg_row = QtWidgets.QHBoxLayout()
        bg_row.addWidget(self.cell_check)
        bg_row.addStretch(1)
        bg_row.addWidget(self._label("Background"))
        bg_row.addWidget(self.bg_button)
        v.addLayout(bg_row)

        section = _section("")
        self._bind(section.setText, "Render")
        v.addWidget(section)
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
        form.addRow(self._label("Antialiasing"), self.aa_spin)
        form.addRow(self._label("Ambient occlusion"), ao_row)
        form.addRow(self._label("Shadows"), self.shadow_check)
        form.addRow(self._label("Brightness"), self.brightness_spin)
        v.addLayout(form)

        section = _section("")
        self._bind(section.setText, "Output")
        v.addWidget(section)
        self.format_group = ToggleGroup(len(FORMATS))
        for button, (key, _) in zip(self.format_group.buttons, FORMATS):
            self._bind(button.setText, key)
        self.format_group.buttons[3].setChecked(True)
        self.format_group.group.idClicked.connect(self._format_changed)
        v.addWidget(self.format_group)

        out = QtWidgets.QFormLayout()
        out.setLabelAlignment(QtCore.Qt.AlignLeft)
        self.size_combo = QtWidgets.QComboBox()
        for i, (key, w, hgt) in enumerate(SIZE_PRESETS):
            self.size_combo.addItem("", (w, hgt))
            self._bind(lambda text, i=i: self.size_combo.setItemText(i, text), key)
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
        out.addRow(self._label("Size"), size_row)

        self.first_spin = _spin(0, 0, 0)
        self.last_spin = _spin(0, 0, 0)
        self.stride_spin = _spin(1, 100000, 1)
        self._bind(self.stride_spin.setPrefix, "@stride_prefix")
        self._bind(self.stride_spin.setSuffix, "@stride_suffix")
        frames_row = QtWidgets.QHBoxLayout()
        frames_row.addWidget(self.first_spin)
        dash = QtWidgets.QLabel("–")
        dash.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        frames_row.addWidget(dash)
        frames_row.addWidget(self.last_spin)
        frames_row.addWidget(self.stride_spin)
        self.frames_label = self._label("Frames")
        out.addRow(self.frames_label, frames_row)
        self.fps_spin = _spin(0.5, 120.0, 20.0, double=True)
        self.fps_spin.setDecimals(1)
        self.fps_spin.setSuffix(" fps")
        self.fps_label = self._label("Rate")
        out.addRow(self.fps_label, self.fps_spin)

        self.out_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("…")
        browse.setObjectName("Icon")
        browse.clicked.connect(self._choose_output)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.out_edit, 1)
        path_row.addWidget(browse)
        out.addRow(self._label("Save to"), path_row)
        v.addLayout(out)

        self.preview_button = QtWidgets.QPushButton()
        self._bind(self.preview_button.setText, "Preview")
        self.preview_button.clicked.connect(lambda: self.render_preview())
        self.export_button = QtWidgets.QPushButton()
        self._bind(self.export_button.setText, "Export")
        self.export_button.setObjectName("Primary")
        self.export_button.clicked.connect(lambda: self.run_export())
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

    def _set_file_text(self, text):
        # Once a file is loaded the button shows its name, which needs no translation.
        self.file_button.setText(self.input_path.name if self.input_path else text)

    # ------------------------------------------------------------ file
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".ovito"):
                self.import_ovito_types(path)
            else:
                self.open_file(path)

    def choose_file(self):
        start = self.settings.value("last_dir", str(Path.home()))
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("Open…"), start)
        if path:
            self.open_file(path)

    @_exclusive
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
            self.types = scan_types(pipeline)
            self._populate_types(self.types)
            self._apply_cell_visibility(self.cell_check.isChecked())
            self.file_button.setText(path.name)
            self.file_button.setToolTip(str(path))
            self.setWindowTitle(f"{path.name} — {APP_NAME}")
            self.out_edit.clear()
            self._suggest_output()
            self._set_loaded(True)
            self._attach_pan_filter()
            self.zoom_all()
            # Fit again once the viewport has been laid out and the first frame evaluated.
            QtCore.QTimer.singleShot(300, lambda: self.zoom_all())
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
        self.step_timer.start()

    @_exclusive
    def _update_step(self):
        if self.pipeline is None:
            return
        timestep = self.pipeline.compute(self.frame_slider.value()).attributes.get("Timestep")
        self.step_label.setText("" if timestep is None else tr("step {n}", n=timestep))

    def _attach_pan_filter(self):
        handle = self.windowHandle()
        for window in QtGui.QGuiApplication.allWindows():
            if handle is not None and window.parent() is handle:
                self.pan_filter.attach(window)

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

    def _set_drag_mode(self, index: int):
        self._attach_pan_filter()
        self.pan_filter.enabled = index == 1

    @_exclusive
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
            color = self.type_style.colors.get(tid, color)
            radius = self.type_style.radii.get(tid, radius)
            row = QtWidgets.QHBoxLayout()
            visible = QtWidgets.QCheckBox()
            visible.setChecked(tid not in self.type_style.hidden)
            visible.toggled.connect(lambda on, t=tid: self._set_type_visible(t, on))
            swatch = QtWidgets.QPushButton()
            swatch.setObjectName("Swatch")
            self._paint_swatch(swatch, color)
            swatch.clicked.connect(lambda _=False, t=tid, b=swatch: self._choose_type_color(t, b))
            radius_spin = _spin(0.0, 10.0, radius, double=True, step=0.1)
            radius_spin.setSpecialValueText(tr("auto"))
            radius_spin.setPrefix("r ")
            radius_spin.setFixedWidth(90)
            radius_spin.valueChanged.connect(lambda val, t=tid: self._set_type_radius(t, val))
            row.addWidget(visible)
            row.addWidget(swatch)
            row.addWidget(QtWidgets.QLabel(name or tr("@type", id=tid)), 1)
            row.addWidget(radius_spin)
            self.types_box.addLayout(row)

    @staticmethod
    def _paint_swatch(button, color):
        code = color_hex(color)
        button.setStyleSheet(f"background-color: {code};")
        button.setToolTip(code)
        button.setProperty("rgb", tuple(float(c) for c in color[:3]))

    def _palette(self) -> list[str]:
        imported = self.settings.value("ovito_palette") or []
        imported = [c for c in ([imported] if isinstance(imported, str) else imported) if parse_color(c)]
        return list(dict.fromkeys(imported + PALETTE))[:24]

    def _pick_color(self, button, apply):
        popup = ColorPopup(button.property("rgb"), self._palette(), self)
        popup.picked.connect(lambda rgb: (self._paint_swatch(button, rgb), apply(rgb)))
        popup.show_below(button)

    def _choose_type_color(self, tid, button):
        def apply(rgb):
            self.type_style.colors[tid] = rgb
            self._refresh_pipeline()

        self._pick_color(button, apply)

    def import_ovito_types(self, path=None):
        """Take type colors and radii from an OVITO session file, matching types by name, then by id."""
        from .session import SessionFormatError, read_particle_types

        if path is None:
            start = self.settings.value("last_dir", str(Path.home()))
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("From .ovito…"), start, "OVITO (*.ovito)")
            if not path:
                return
        try:
            found = read_particle_types(path)
        except (OSError, SessionFormatError) as exc:
            QtWidgets.QMessageBox.warning(self, APP_NAME, f"{Path(path).name}\n\n{exc}")
            return
        codes = list(dict.fromkeys(color_hex(color) for _, color, _ in found.values()))
        self.settings.setValue("ovito_palette", codes[:8])
        by_name = {name.lower(): entry for name, *entry in found.values() if name}
        matched = 0
        for tid, (name, _, _) in self.types.items():
            entry = by_name.get((name or "").lower())
            if entry is None and tid in found:
                entry = found[tid][1:]
            if entry is None:
                continue
            color, radius = entry
            self.type_style.colors[tid] = color
            if radius:
                self.type_style.radii[tid] = radius
            matched += 1
        if self.types and not matched:
            QtWidgets.QMessageBox.information(self, APP_NAME, tr("No atom types match {name}.", name=Path(path).name))
            return
        self._populate_types(self.types)
        self._refresh_pipeline()

    def _set_type_visible(self, tid, on: bool):
        if on:
            self.type_style.hidden.discard(tid)
        else:
            self.type_style.hidden.add(tid)
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
        def apply(rgb):
            self.background = rgb
            self.scene.render_settings.background_color = rgb

        self._pick_color(self.bg_button, apply)

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
            path = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Save to"), current)
        else:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Save to"), current, f"*{FORMAT_SUFFIX[fmt]}")
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

    @_exclusive
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

    @_exclusive
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
            answer = QtWidgets.QMessageBox.question(self, APP_NAME, tr("Replace {name}?", name=Path(out).name))
            if answer != QtWidgets.QMessageBox.Yes:
                return
        frames = [self.frame_slider.value()] if fmt == "png" else self._frames()

        self.play_button.setChecked(False)
        dialog = QtWidgets.QProgressDialog("", tr("Cancel"), 0, len(frames), self)
        dialog.setWindowTitle(tr("Export"))
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setMinimumWidth(420)
        dialog.setValue(0)

        def progress(done, total, _message):
            dialog.setMaximum(total)
            dialog.setValue(done)
            if done < len(frames):
                dialog.setLabelText(tr("Frame {frame}  ·  {i} / {n}", frame=frames[done], i=done + 1, n=len(frames)))
            elif fmt in ("gif", "mp4") and done < total:
                dialog.setLabelText(tr("Encoding {fmt}", fmt=fmt.upper()))
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
        reveal = box.addButton(tr("Show in folder"), QtWidgets.QMessageBox.ActionRole)
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
        save = QtWidgets.QPushButton(tr("Save…"))
        save.clicked.connect(self._save)
        close = QtWidgets.QPushButton(tr("Close"))
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

        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Save…"), str(Path.home() / "render.png"), "*.png")
        if path:
            write_png(path if path.lower().endswith(".png") else path + ".png", self.image)


if __name__ == "__main__":
    sys.exit(main())
