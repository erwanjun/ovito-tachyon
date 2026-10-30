"""Qt stylesheet built from the shadcn/ui design tokens (neutral base, light and dark).

Token values follow shadcn/ui's default theme (MIT); the oklch neutrals map to
Tailwind's neutral palette.
"""

from __future__ import annotations

from pathlib import Path

LIGHT = {
    "background": "#ffffff",
    "foreground": "#0a0a0a",
    "card": "#ffffff",
    "primary": "#171717",
    "primary_fg": "#fafafa",
    "secondary": "#f5f5f5",
    "muted_fg": "#737373",
    "accent": "#f5f5f5",
    "border": "#e5e5e5",
    "ring": "#a1a1a1",
    "sidebar": "#fafafa",
}

DARK = {
    "background": "#0a0a0a",
    "foreground": "#fafafa",
    "card": "#171717",
    "primary": "#e5e5e5",
    "primary_fg": "#171717",
    "secondary": "#262626",
    "muted_fg": "#a1a1a1",
    "accent": "#262626",
    "border": "#2e2e2e",
    "ring": "#737373",
    "sidebar": "#171717",
}

_CHECK = ('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" '
          'stroke="{c}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>')
_CHEVRON = ('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" '
            'stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>')


def _icons(t: dict, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, svg, color in (("check", _CHECK, t["primary_fg"]), ("chevron", _CHEVRON, t["muted_fg"])):
        path = folder / f"{name}-{color.lstrip('#')}.svg"
        if not path.exists():
            path.write_text(svg.format(c=color), encoding="utf-8")
        out[name] = path.as_posix()
    return out


def stylesheet(dark: bool, icon_dir: Path) -> str:
    t = DARK if dark else LIGHT
    i = _icons(t, icon_dir)
    return f"""
* {{ font-size: 13px; color: {t['foreground']}; }}
QMainWindow, QDialog {{ background: {t['background']}; }}
#Sidebar, #Sidebar QWidget#SidebarBody {{ background: {t['sidebar']}; }}
#Sidebar {{ border-left: 1px solid {t['border']}; }}
#BottomBar {{ background: {t['background']}; border-top: 1px solid {t['border']}; }}
QLabel#Section {{ font-weight: 600; font-size: 12px; color: {t['muted_fg']}; padding-top: 10px; }}
QLabel#Muted {{ color: {t['muted_fg']}; }}
QLabel#Title {{ font-weight: 600; font-size: 14px; }}
QFrame#Separator {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton {{
  background: {t['background']}; border: 1px solid {t['border']}; border-radius: 6px;
  padding: 0 12px; min-height: 30px; font-weight: 500;
}}
QPushButton:hover {{ background: {t['accent']}; }}
QPushButton:pressed {{ background: {t['border']}; }}
QPushButton:disabled {{ color: {t['muted_fg']}; }}
QPushButton:focus {{ border-color: {t['ring']}; }}
QPushButton#Primary {{ background: {t['primary']}; color: {t['primary_fg']}; border: 1px solid {t['primary']}; }}
QPushButton#Primary:hover {{ background: {t['muted_fg']}; border-color: {t['muted_fg']}; }}
QPushButton#Primary:disabled {{ background: {t['border']}; border-color: {t['border']}; color: {t['muted_fg']}; }}
QPushButton#Toggle {{ border: 1px solid transparent; background: transparent; padding: 0 8px; }}
QPushButton#Toggle:hover {{ background: {t['accent']}; }}
QPushButton#Toggle:checked {{ background: {t['background']}; border: 1px solid {t['border']}; }}
QWidget#ToggleGroup {{ background: {t['secondary']}; border-radius: 8px; }}
QPushButton#Swatch {{ min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0; border-radius: 11px; }}
QPushButton#Icon {{ min-width: 30px; max-width: 30px; padding: 0; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: {t['background']}; border: 1px solid {t['border']}; border-radius: 6px;
  padding: 0 8px; min-height: 30px; selection-background-color: {t['ring']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {t['ring']}; }}
QSpinBox, QDoubleSpinBox {{ padding: 0 6px; }}
QAbstractSpinBox QLineEdit {{ border: none; padding: 0; min-height: 0; background: transparent; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
  subcontrol-origin: border; width: 0; height: 0; border: none;
}}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {t['muted_fg']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({i['chevron']}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
  background: {t['card']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px;
  selection-background-color: {t['accent']}; selection-color: {t['foreground']}; outline: none;
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['primary']}; border-radius: 4px; background: {t['background']}; }}
QCheckBox::indicator:checked {{ background: {t['primary']}; image: url({i['check']}); }}

QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['secondary']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['primary']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
  width: 16px; height: 16px; margin: -7px 0; border-radius: 8px;
  background: {t['background']}; border: 1px solid {t['primary']};
}}

QProgressBar {{ background: {t['secondary']}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t['primary']}; border-radius: 4px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 8px; background: transparent; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {t['primary']}; color: {t['primary_fg']}; border: none; padding: 4px 8px; border-radius: 6px; }}
QMenuBar {{ background: {t['background']}; }}
QFrame#Popover {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QPushButton#Link {{ border: none; background: transparent; padding: 0; min-height: 0; color: {t['muted_fg']}; }}
QPushButton#Link:hover {{ color: {t['foreground']}; text-decoration: underline; }}
QMenu {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['accent']}; }}
"""
