# 参与贡献

欢迎提交问题和 Pull Request。当前项目主要面向 Windows 10/11、Python 3.12 x64。

## 开发

```powershell
git clone https://github.com/zijichiji0114-code/HoverTranslate.git
cd HoverTranslate
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-lock.txt
.venv\Scripts\python.exe main.py
```

也可先运行 `setup.ps1`。修改前先说明要解决的问题，保持改动集中。涉及快捷键、取词、异步取消和浮窗隐藏的修改，应验证两种翻译方式，并防止过期响应重新弹出。

```powershell
.venv\Scripts\python.exe -m pytest -q
.\build.ps1 -OutputDirectory dist
.venv\Scripts\python.exe scripts\check_packaged_selection.py dist\HoverTranslate\HoverTranslate.exe
```

测试使用本机 OCR 和模拟 API，不需要真实密钥。提交问题时说明 Windows 版本、显示器缩放、所用应用、触发方式以及复现步骤。请删除截图和日志中的 API Key、原文隐私及个人路径。

## 发布

程序目录需整体压缩，保留 `LICENSE`、`THIRD_PARTY_NOTICES.md`、`licenses` 和 OCR 模型。不要把 `.venv`、用户配置、日志、缓存或编译产物提交到 Git；便携包通过 GitHub Releases 分发。

项目源代码使用 MIT 许可证。第三方库、模型和字体仍按各自许可证使用。
