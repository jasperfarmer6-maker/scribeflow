# 模型说明

> 文档状态：已验证事实｜最后验证：2026-08-01

## MinerU OCR 模型

MinerU 在本机执行 OCR/版面解析，默认 `backend=pipeline`、`method=ocr`、`language=ch`、`model_source=modelscope`。模型不随 App 打包，首次运行可能从模型源下载并使用用户缓存。

## AI 清洗模型

AI 是可选的 OpenAI 兼容 Chat Completions 服务。当前调用固定使用 `temperature=0`，优先请求 JSON object；服务不支持时退回兼容模式。模型只返回：

- `drop_ids`
- `drop_reasons`
- `merge_groups`
- `heading_levels`

程序验证块 ID、相邻关系、标题范围，并忽略其它字段。

## 开发者诊断

运行期间通过 `model_info` 事件报告模型名、来源、路径可见性和参数。上游未暴露真实缓存路径时显示“路径未由 MinerU 暴露”，不伪造路径。
