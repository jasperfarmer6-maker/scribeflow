# 模块边界

> 文档状态：已验证事实｜最后验证：2026-08-01

| 模块 | 输入 | 输出 | 边界 |
|---|---|---|---|
| `cli.py` | 命令行参数、环境变量 | `PipelineConfig`、退出码 | 不实现转换规则 |
| `gui_backend.py` | CLI 参数 | JSON Lines 事件 | 不绘制界面 |
| `pipeline.py` | `PipelineConfig` | 输出目录、诊断事件 | 负责编排和发布 |
| `content.py` | MinerU JSON、`Block` | 清洗后块、Markdown | 不调用网络模型 |
| `ai_cleaner.py` | `Block`、`AIConfig` | 受限操作对象 | 不改写正文 |
| `models.py` | 数据字段 | `Block`、`AIConfig`、`PipelineConfig` | 纯数据模型 |
| SwiftUI | 用户操作、JSONL | GUI 状态 | 不持有 OCR 逻辑 |

主要接口是 `run_pipeline(config, progress_callback, console_stream)`、`request_ai_operations(blocks, config, logger)` 和 `ProgressCallback`。
