# 依赖列表

> 文档状态：已验证事实｜最后验证：2026-08-01

| 层 | 依赖 | 版本/来源 |
|---|---|---|
| 运行时 | Python | 3.12 |
| OCR | MinerU | 3.4.4（构建产物记录） |
| AI | openai | `>=1.70,<3` |
| PDF | pypdf | `>=6,<7` |
| 配置 | python-dotenv | `>=1,<2` |
| GUI | SwiftUI/AppKit + 完整 Xcode | macOS 14+，Apple Silicon 构建；仅 CommandLineTools 不足 |

`uv.lock` 是 Python 依赖解析来源。App 将 Python、site-packages、项目后端和 MinerU 一起打包，但不打包 OCR 模型缓存。
