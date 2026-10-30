# ovito-tachyon

![OVITO-Tachyon](docs/screenshot.png)

用独立编译的 [Tachyon](https://github.com/erwanjun/ovito-tachyon/tree/main/vendor/tachyon) 光线追踪器渲染分子动力学轨迹：
桌面软件可以直接打开 LAMMPS 等轨迹文件，自由旋转视角，导出 PNG、图片序列、GIF 或 MP4；
同时也是一个可以在 OVITO Python 脚本里调用的渲染库。

## 桌面软件

在 [Releases](https://github.com/erwanjun/ovito-tachyon/releases) 下载：

| 系统 | 文件 |
|---|---|
| macOS（Apple 芯片） | `OVITO-Tachyon-<版本>-macOS-arm64.dmg`，打开后拖进“应用程序” |
| Windows 10/11 x64 | `OVITO-Tachyon-<版本>-Windows-x64-setup.exe`，或免安装的 `…-portable.zip` |

安装包没有付费代码签名，第一次打开时系统会拦一下：

- macOS：在“应用程序”里右键点 OVITO-Tachyon → 打开 → 打开。仍被拦时运行
  `xattr -dr com.apple.quarantine /Applications/OVITO-Tachyon.app`。
- Windows：SmartScreen 提示时点“更多信息” → “仍要运行”。

用法：打开轨迹文件（或直接拖进窗口）→ 在视口里拖动旋转、右键/中键拖动平移、滚轮缩放，
或点右侧的视角按钮 → 选择格式、分辨率、帧范围和帧率 → Export。视口里的白色区域就是导出画面的范围。
支持 OVITO 能读取的所有格式（LAMMPS dump/data、XYZ、POSCAR、PDB、GSD 等）。

## Python 库

```bash
pip install ovito ovito-tachyon
```

wheel 内置 Tachyon 可执行文件，`pip install` 后即可使用，无需另外安装渲染器。

### 用法

```python
from ovito.io import import_file
from ovito.vis import Viewport
from ovito_tachyon import TachyonExporter

pipeline = import_file("dump.lammpstrj")
pipeline.add_to_scene()

vp = Viewport(type=Viewport.Type.Perspective, camera_dir=(-1, -0.6, -0.5))
vp.zoom_all(size=(1600, 1200))

TachyonExporter(ambient_occlusion_samples=16).render(
    "out.png", viewport=vp, size=(1600, 1200), frame=0)
```

参数名与 `ovito.vis.TachyonRenderer` 保持一致：`antialiasing`、`antialiasing_samples`、
`ambient_occlusion`、`ambient_occlusion_brightness`、`ambient_occlusion_samples`、`direct_light`、
`direct_light_intensity`、`shadows`、`depth_of_field`、`focal_length`、`aperture`、`max_ray_recursion`。
另外还有 `material=Material(...)`（漫反射/高光等）和 `threads`。

默认光照逐像素拟合了 OVITO 自带 TachyonRenderer 的默认效果，两者的差异在采样噪声范围内。
想更亮时调高环境光，例如 `Material(ambient=0.4)`；`Material(phong=0.3)` 可加上高光。

`render()` 的参数：

| 参数 | 说明 |
|---|---|
| `filename` | `.png` 或 `.ppm`；为 `None` 时只返回数组 |
| `viewport` | `ovito.vis.Viewport`；省略时使用 (-1,-1,-1) 方向透视并自动缩放 |
| `pipelines` | 默认 `ovito.scene.pipelines`；也可以直接传入一个或多个 Pipeline |
| `zoom_all` | 按渲染几何体重新调整相机距离（无 viewport 时默认开启） |
| `scene_file` | 另存生成的 Tachyon 场景文件 `.dat`，便于调试或手工修改 |

返回值是 `(高, 宽, 3)` 的 `uint8` numpy 数组。批量出图可用
`exporter.render_animation("frames/img_{:04d}.png", range(0, 100, 5), viewport=vp, size=(800, 600))`。

### 命令行

```bash
ovito-tachyon dump.lammpstrj -o out.png --size 1600 1200 --view top --frame -1
ovito-tachyon --which        # 显示正在使用的 tachyon 可执行文件
```

### 支持的内容

- 粒子：球形；半径按 `Radius` 属性 → 类型半径 → `ParticlesVis.radius` 的顺序取值，并乘以缩放系数；
  颜色按 `Color` → 类型颜色取值；`Transparency` 属性生效；被选中的粒子显示为红色
- 键：半键着色（`BondsVis.coloring_mode` / 旧版 `use_particle_colors`）、键的 `Color` 和 `Transparency` 属性、跨周期边界的键
- 模拟晶胞：`line_width`、`rendering_color`、`render_cell`
- 相机：透视/正交，与 OVITO 的 `fov` 定义一致；支持景深

暂不支持：表面网格（SurfaceMesh）、位错线、非球形粒子（按球形渲染并给出警告）、
周期性镜像、视口叠加层（文字、色标）、透明背景。

### 可执行文件的查找顺序

1. 环境变量 `OVITO_TACHYON_EXE`
2. 包内 `ovito_tachyon/bin/tachyon`
3. `PATH` 中的 `tachyon`（例如 `conda install -c conda-forge tachyon`）

## 构建与发布

```bash
pip install build
python -m build            # dist/ 下生成 sdist 和当前平台的 wheel
```

构建 wheel 时，`setup.py` 会用系统 C 编译器把 `vendor/tachyon` 编译进包内（macOS 需要 Xcode
Command Line Tools，Linux 需要 gcc，Windows 需要 MSVC）。wheel 的标签是 `py3-none-<平台>`，
同一平台的所有 Python 3 版本通用。仓库不能放在 exFAT 分区上构建（会报找不到 egg-info）。

桌面软件：

```bash
pip install dist/*.whl ovito imageio-ffmpeg pyinstaller pillow
pyinstaller packaging/ovito-tachyon.spec      # dist/OVITO-Tachyon.app 或 dist/OVITO-Tachyon/
sh packaging/build_dmg.sh 0.1.0               # macOS：release/*.dmg
```

推送 `v*` tag 后，`.github/workflows/release.yml` 会在 GitHub Actions 上构建 macOS arm64 的 dmg 和
Windows x64 的安装包及免安装 zip，先在打包好的程序里跑一遍 `--selftest`（渲染并编码 GIF/MP4），
再发布到 Releases。`wheels.yml` 可手动触发，用 cibuildwheel 构建各平台的 Python wheel。

## 许可

本包代码使用 MIT 许可；随附的 Tachyon 0.99b6（John E. Stone）使用 BSD 3-clause 许可，见 `LICENSE`。
桌面软件还打包了 OVITO Python 模块（MIT）、Qt for Python / PySide6（LGPLv3）和 imageio-ffmpeg 提供的 FFmpeg（GPL）。
