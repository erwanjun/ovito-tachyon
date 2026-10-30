import pytest

pytest.importorskip("PySide6")

from ovito_tachyon.app import color_hex, parse_color  # noqa: E402


@pytest.mark.parametrize("text, rgb", [
    ("#ff6666", (1.0, 0.4, 0.4)),
    ("FF6666", (1.0, 0.4, 0.4)),
    ("#f66", (1.0, 0.4, 0.4)),
    ("255, 102, 102", (1.0, 0.4, 0.4)),
    ("1 0.4 0.4", (1.0, 0.4, 0.4)),
    ("1, 1, 1", (1.0, 1.0, 1.0)),
])
def test_parse_color(text, rgb):
    assert parse_color(text) == pytest.approx(rgb)


@pytest.mark.parametrize("text", ["", "#12345", "zz", "300, 0, 0", "1, 2"])
def test_parse_color_rejects(text):
    assert parse_color(text) is None


def test_color_hex():
    assert color_hex((1.0, 0.4, 0.4)) == "#ff6666"
