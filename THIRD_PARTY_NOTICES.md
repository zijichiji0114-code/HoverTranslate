# 第三方组件与素材

HoverTranslate 自有源代码采用根目录中的 MIT 许可证。它不改变所依赖组件的许可条件。项目不包含 API Key，也不包含大语言模型权重。

| 组件 | 用途 | 上游与许可证 |
|---|---|---|
| PySide6 Essentials / Shiboken6 / Qt | 桌面界面 | [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)，按对应组件的 LGPL/GPL 或其他上游条款使用；本项目采用动态链接 |
| RapidOCR | 本机文字识别 | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)，Apache-2.0 |
| PaddleOCR 衍生 ONNX 模型 | 检测、方向分类、识别 | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)，Apache-2.0；模型随 rapidocr-onnxruntime 安装 |
| ONNX Runtime | OCR 推理 | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime)，MIT；同时保留其 ThirdPartyNotices |
| OpenCV | 图像处理 | [opencv/opencv](https://github.com/opencv/opencv)，具体构建的许可与附带组件声明见运行包 |
| NumPy | 图像数组 | [numpy/numpy](https://github.com/numpy/numpy)，BSD-3-Clause 及其附带声明 |
| httpx / httpcore | API 请求 | [encode/httpx](https://github.com/encode/httpx)、[encode/httpcore](https://github.com/encode/httpcore)，BSD-3-Clause |
| mss | 屏幕区域截图 | [python-mss/python-mss](https://github.com/python-mss/python-mss)，MIT |
| comtypes | Windows UI Automation | [enthought/comtypes](https://github.com/enthought/comtypes)，MIT |
| Pillow | 图标导出 | [python-pillow/Pillow](https://github.com/python-pillow/Pillow)，HPND 及对应构建的附带声明 |

完整版本以 `requirements-lock.txt` 为准。打包脚本调用 `scripts/collect_licenses.py`，复制当前环境中分发包自带的许可文件，并在便携包内生成 `licenses/manifest.json`；发布者需保留这些文件。预置标准许可文本位于 `third_party_licenses/`。

Qt 的 DLL 与应用分开放置，可按上游许可要求替换；本仓库提供应用源码与构建步骤。PyInstaller 仅用于打包，其许可例外说明见 [PyInstaller 上游](https://pyinstaller.org/en/stable/license.html)。

图标生成脚本通过 Windows 系统已安装的 Microsoft YaHei Bold 字体绘制“译”字，仓库只提供最终图形，不分发字体文件。重新生成图标需要自行具备该字体的使用权；也可直接使用已有 PNG、SVG 和 ICO。
