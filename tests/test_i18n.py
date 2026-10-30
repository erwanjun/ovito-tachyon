import pytest

from ovito_tachyon import i18n


@pytest.fixture(autouse=True)
def _reset():
    yield
    i18n.set_language("en")


def test_english_is_identity_except_special_keys():
    i18n.set_language("en")
    assert i18n.tr("Export") == "Export"
    assert i18n.tr("@stride_prefix") == "every "
    assert i18n.tr("@type", id=3) == "Type 3"


def test_chinese():
    i18n.set_language("zh")
    assert i18n.tr("Export") == "导出"
    assert i18n.tr("step {n}", n=500) == "时间步 500"
    assert i18n.tr("@type", id=2) == "类型 2"
    assert i18n.tr("not translated") == "not translated"


def test_every_chinese_key_formats():
    i18n.set_language("zh")
    for key in i18n._ZH:
        i18n.tr(key, id=1, n=1, name="x", frame=1, i=1, fmt="MP4")


def test_unknown_language():
    with pytest.raises(ValueError):
        i18n.set_language("fr")
