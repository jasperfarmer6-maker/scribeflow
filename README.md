# 扫描版 PDF 转 Markdown

在 macOS 本地调用 MinerU 识别扫描版 PDF，再以“块级操作”完成保真清洗，保留标题、正文、表格和图片，并按章节输出多个 Markdown 文件。

## 功能

- 强制 OCR 或自动判断 PDF 类型
- 删除 MinerU 标记的页眉、页脚和页码
- 规则删除明确的广告、推广文字和独立页码
- 可选使用 AI 判断广告、断句合并和标题层级；默认关闭
- AI 只能返回块 ID 操作，不能重写、润色或替换正文
- 保留 MinerU 提取的图片，并修复完整文档和章节文件中的相对链接
- 根据标题层级自动拆分章节
- 输出运行日志、清洗审计、运行清单和 MinerU 原始结果
- 使用暂存目录和原子发布，避免失败时留下“看似成功”的半成品
- 根据 PDF 页数自动放宽 MinerU 任务超时：最少 4 小时、每页预留 60 秒、最长 24 小时
- 厚文档自动降低 MinerU 单批页数，减少内存峰值及本地 OCR 服务重启
- 默认按 16 页分段顺序 OCR，每段完成后保存 checkpoint，支持失败后续跑
- 校验页码覆盖、分段状态、输入哈希和资源引用，全部完成后才发布最终目录

## 环境

当前项目使用：

- Python 3.12
- MinerU 3.4.4
- macOS Apple Silicon
- 默认模型源：ModelScope

## 从源码构建 macOS 桌面应用

本仓库只发布源码，不提供已打包的 `.app`、OCR 模型或第三方运行时。构建本地应用前，请先完成依赖安装，并准备完整 Xcode 与独立 Python 3.12 运行时。

```text
uv sync
uv run python macos/build_app.py
```

构建完成后，应用位于 `dist/PDF 转 Markdown.app`。双击应用后，把扫描版 PDF 拖入窗口、选择输出目录，再点击“开始转换”即可。应用会显示 OCR、章节分析和 Markdown 生成状态；成功后自动打开输出文件夹，并显示 Markdown 与章节数量。失败时可直接在窗口中查看错误日志。

应用已内置 Python 3.12、MinerU 和项目后端，不依赖本项目的 `.venv`，日常使用无需打开终端。OCR 模型沿用当前用户的 ModelScope 缓存；新机器第一次使用时需要联网下载模型。

若自动识别的 Python 运行时不符合要求，可显式指定：

```bash
uv run python macos/build_app.py --python-runtime /path/to/python-3.12-runtime
```

构建脚本会编译 SwiftUI、复制独立运行时、生成图标、执行本地代码签名，并将成品原子发布到 `dist/`。

激活虚拟环境：

```bash
source .venv/bin/activate
```

## AI 配置

复制环境变量示例：

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
PDF2MD_AI_MODEL=你的模型名称
PDF2MD_AI_API_KEY=你的密钥
PDF2MD_AI_BASE_URL=https://你的兼容接口/v1
```

`PDF2MD_AI_BASE_URL` 可省略，省略时使用 OpenAI 默认接口。也兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL`。

密钥不会写入日志、清洗审计或输出清单。

启用 AI 清洗时，待处理 PDF 的内容块会发送给你配置的 OpenAI 或兼容服务。请仅处理你有权发送给该服务的内容，并在启用前确认服务的数据处理政策。

## 一条命令运行完整流水线

```bash
.venv/bin/python scripts/convert_pdf.py \
  "/绝对路径/输入.pdf" \
  --output "/绝对路径/输出文件夹"
```

启用在线 AI 时必须显式添加 `--use-ai` 并配置模型和密钥：

```bash
.venv/bin/python scripts/convert_pdf.py \
  "/绝对路径/输入.pdf" \
  --output "/绝对路径/输出文件夹" \
  --use-ai \
  --ai-model "模型名称"
```

长文档默认每段 16 页；可用 `--segment-pages 8` 等值调整。任务中断后使用相同输入、输出目录和分段大小加 `--resume`，程序会跳过已完成分段。

重复运行并安全替换该工具上次生成的输出：

```bash
.venv/bin/python scripts/convert_pdf.py \
  "/绝对路径/输入.pdf" \
  --output "/绝对路径/输出文件夹" \
  --overwrite
```

默认参数适合中文扫描件：

```text
backend      pipeline
method       ocr
lang         ch
model-source modelscope
```

查看全部参数：

```bash
.venv/bin/python scripts/convert_pdf.py --help
```

安装项目后也可以使用：

```bash
.venv/bin/pdf2md input.pdf -o output/book
```

## 输出结构

```text
指定输出文件夹/
├── document.md              # 清洗后的完整文档
├── chapters/                # 按章节拆分的 Markdown
│   ├── 001-第一章.md
│   └── 002-第二章.md
├── assets/                  # MinerU 提取的图片
├── raw/mineru/              # MinerU 原始结果，便于排错和追溯
├── job_manifest.json        # 分段 checkpoint、页码范围、耗时和恢复状态
├── cleaning_audit.json      # 每次删除、合并、层级调整的原因和原文
├── manifest.json            # 输入、参数、章节和产物清单
└── logs/pipeline.log        # 完整日志
```

使用 `--discard-raw` 可在成功后删除 `raw/`，不影响最终 Markdown 和图片。

## 保真原则

AI 收到带 ID 的内容块，只能返回：

- `drop_ids`：页眉、页脚、页码、广告或推广块
- `merge_groups`：需要合并的相邻断句
- `heading_levels`：已有标题的层级调整

AI 响应中没有“替换正文”字段。程序还会验证块 ID、相邻关系、标题类型和层级范围；无效操作会被忽略。所有有效操作记录在 `cleaning_audit.json`，便于逐条复核。

## 版权与许可

本项目源码按 [MIT License](LICENSE) 发布。依赖及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本工具不授予你处理、上传或分发任何第三方 PDF、图片、OCR 输出或模型文件的权利。请只转换你拥有版权、获得授权或依法可以处理的文件。若你基于 MinerU 向第三方提供在线服务，应按 MinerU 的许可要求在界面或公开文档中清晰标注其使用情况。

## 错误处理

- 缺少输入或 MinerU CLI 时，在执行前给出明确错误；AI 仅在 `--use-ai` 时检查配置。
- MinerU 或 AI 请求失败时返回非零退出码。
- 失败现场保存为 `输出文件夹.failed-时间戳/`，其中包含 checkpoint、日志和已产生的原始文件；可用 `--resume` 继续。
- 已存在的输出目录默认不会覆盖；只有显式传入 `--overwrite` 才会替换。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

生成 300/500 页连续压力样本（只重复源 PDF 第一页，用于耐久性和恢复测试）：

```bash
.venv/bin/python scripts/generate_stress_pdf.py samples/mineru_smoke_test.pdf /tmp/ocr-300.pdf --pages 300
```

## 文档与开发者模式

完整技术文档位于 [`docs/README.md`](docs/README.md)，中文技术白皮书源文件为
[`docs/whitepaper.md`](docs/whitepaper.md)。文档门禁和白皮书生成命令：

```bash
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/build_whitepaper_pdf.py
```

在 macOS 应用的“转换设置”中开启“开发者模式”，即可实时查看当前 OCR/AI 模型、模型源、路径可见性、运行参数和版本信息。API 密钥不会进入诊断事件、日志或 manifest。
