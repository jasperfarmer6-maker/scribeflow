# 配置参考

> 文档状态：已验证事实｜最后验证：2026-08-01

## CLI 参数

`input_pdf`、`--output`、`--overwrite`、`--use-ai`、`--no-ai`、`--ai-model`、`--ai-base-url`、`--backend`、`--method {auto,txt,ocr}`、`--lang`、`--model-source {modelscope,huggingface,local}`、`--chapter-level 1-6`、`--discard-raw`、`--mineru-bin`、`--segment-pages`、`--resume`。

## 环境变量

| 变量 | 用途 |
|---|---|
| `PDF2MD_AI_MODEL` / `OPENAI_MODEL` | AI 模型名 |
| `PDF2MD_AI_API_KEY` / `OPENAI_API_KEY` | AI 密钥；不进入日志和事件 |
| `PDF2MD_AI_BASE_URL` / `OPENAI_BASE_URL` | OpenAI 兼容地址 |
| `MINERU_TASK_RESULT_TIMEOUT_SECONDS` | 覆盖 OCR 等待上限 |
| `MINERU_PROCESSING_WINDOW_SIZE` | 覆盖每批处理页数 |

默认超时至少 4 小时，按每页 60 秒估算，最多 24 小时。页数达到 160/80 时处理窗口自动降为 16/32 页，否则为 64 页。

应用层默认每段 16 页，分段任务顺序执行。每段状态写入 `job_manifest.json`；`--resume` 只继续输入哈希和分段大小均匹配的现场。

GUI 的 API 密钥保存到 macOS 钥匙串；开发者模式默认关闭，只控制诊断面板显示，不改变转换行为。
