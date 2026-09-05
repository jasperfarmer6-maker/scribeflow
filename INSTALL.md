# ScribeFlow 安装与恢复

仓库：https://github.com/jasperfarmer6-maker/scribeflow （公开）
发布：https://github.com/jasperfarmer6-maker/scribeflow/releases/tag/backup-2026-09-05
应用附件：`ScribeFlow-backup-2026-09-05-macos-arm64.zip`

## 新电脑要求与验证边界

- Apple Silicon（M 系列）Mac；**本安装包最低要求 macOS 15.0**，来自已打包依赖的 Mach-O 最低系统声明。仅在 macOS 27.0 上完成本次验证；没有在其他系统版本或另一台电脑实测。
- 应用内含 Python 3.12 与运行依赖；安装预构建 ZIP 不需要项目目录、虚拟环境或 Xcode。
- 本版本采用本地 ad-hoc 签名，没有 Apple Developer ID 公证。只从自己的 GitHub 仓库下载并核对校验和；首次打开若被拦截，在系统设置 → 隐私与安全性查看对应应用的“仍要打开”。不要关闭系统安全检查。

## 下载与安装

1. 打开仓库的 Releases，选择 `backup-2026-09-05`，下载应用 ZIP 与 `SHA256SUMS.txt`。私有仓库需要先登录有权限的 GitHub 账号。
2. 在下载目录运行 `shasum -a 256 -c SHA256SUMS.txt`，确认应用 ZIP 显示 `OK`（同时下载校验清单列出的安装说明）。
3. 解压 ZIP，将 `.app` 拖到“应用程序”目录。已有同名应用时，先将旧副本保存到备份目录，再安装新副本。
4. 模型准备好后选择自己的输入文件和独立输出目录。安装包不包含任何个人媒体、转换结果或 API 密钥。

## 备份内容与恢复边界

- 源码与历史在 Git 仓库中；应用 ZIP、说明和校验文件在 Releases 中。
- `Contents/Resources/BuildInfo.json` 记录构建对应的源码提交；`Licenses/` 包含依赖清单和许可文件，依赖包原始许可也保留在运行时中。
- 不包含个人 PDF/视频、处理结果、任务历史、模型缓存、`.env`、钥匙串密钥或其他电脑数据。
- 尚需的模型在新电脑重新下载。若要保留以前的任务或结果，需要另行备份自己的数据；本次没有删除或迁移这些数据。
- 应用改名、路径中含空格或中文不应影响包内 Python 启动。不要自行改动 Bundle 内部文件，以免破坏签名。

## OCR 模型与可选 AI

本程序使用 MinerU，默认模型源为 ModelScope，首次转换需要联网获取模型；缓存位于当前用户目录。模型体积与所需识别组件有关，建议预留至少 10 GB 供模型、下载缓存和任务临时文件使用。模型准备好后，关闭可选在线 AI 即可在本机处理。

可选 AI 默认关闭。旧电脑钥匙串中的 API 密钥和 `.env` 不会随程序备份；需要时在新电脑自行重新配置。启用在线 AI 会把待处理内容发送到你配置的服务。

## 从源码构建

安装完整 Xcode 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后执行：

```bash
git clone https://github.com/jasperfarmer6-maker/scribeflow.git
cd scribeflow
git checkout backup-2026-09-05
uv python install 3.12
uv sync --frozen
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer uv run --frozen python macos/build_app.py
```

若安装的是 Xcode beta，将 `DEVELOPER_DIR` 改为其实际路径。产物位于 `dist/ScribeFlow.app`；`--output` 可指定构建目录，`--python-runtime` 可指定独立运行时。构建不会删除 `/Applications` 中的应用，也不允许直接将构建输出设在该目录。

保持原技术身份：可执行文件 `PDFToMarkdown`、Bundle ID `com.local.PDFToMarkdown`，CLI 为 `pdf2md`，原环境变量 `PDF2MD_*` 继续有效。
