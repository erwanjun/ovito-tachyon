"""UI strings in English and Chinese. Keys are the English text; ``@``-keys have no English literal."""

from __future__ import annotations

LANGUAGES = {"en": "English", "zh": "中文"}

_EN = {
    "@stride_prefix": "every ",
    "@stride_suffix": "",
    "@type": "Type {id}",
}

_ZH = {
    "Open trajectory": "打开轨迹",
    "Open…": "打开…",
    "View": "视角",
    "Persp": "透视",
    "Ortho": "正交",
    "Top": "顶视",
    "Bottom": "底视",
    "Front": "前视",
    "Back": "后视",
    "Left": "左视",
    "Right": "右视",
    "Fit": "适配",
    "Rotate": "旋转",
    "Pan": "平移",
    "Atoms": "原子",
    "@type": "类型 {id}",
    "auto": "自动",
    "Box": "模拟盒",
    "Background": "背景",
    "Render": "渲染",
    "Antialiasing": "抗锯齿",
    "Ambient occlusion": "环境光遮蔽",
    "Shadows": "阴影",
    "Brightness": "亮度",
    "Output": "输出",
    "Sequence": "序列",
    "Size": "尺寸",
    "Square": "方形",
    "Custom": "自定义",
    "Frames": "帧",
    "@stride_prefix": "每 ",
    "@stride_suffix": " 帧",
    "Rate": "帧率",
    "Save to": "保存到",
    "Preview": "预览",
    "Export": "导出",
    "File": "文件",
    "Quit": "退出",
    "Language": "语言",
    "step {n}": "时间步 {n}",
    "Replace {name}?": "替换 {name}？",
    "Show in folder": "在文件夹中显示",
    "Cancel": "取消",
    "Frame {frame}  ·  {i} / {n}": "第 {frame} 帧  ·  {i} / {n}",
    "Encoding {fmt}": "正在编码 {fmt}",
    "Save…": "保存…",
    "Close": "关闭",
}

_TABLES = {"en": _EN, "zh": _ZH}
_current = "en"


def set_language(lang: str) -> None:
    global _current
    if lang not in LANGUAGES:
        raise ValueError(f"unsupported language {lang!r}")
    _current = lang


def language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    text = _TABLES[_current].get(key, _EN.get(key, key))
    return text.format(**kwargs) if kwargs else text
