"""通过 OpenAI 兼容接口产生受限的块级清洗操作。"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable

from openai import OpenAI

from .errors import PipelineError
from .models import AIConfig, Block


SYSTEM_PROMPT = """你是文档格式清洗器。必须保护原文，禁止改写、润色、摘要、翻译、纠错或生成替代文本。
你只能对给定块 ID 返回以下操作：
1. drop_ids：删除明确的页眉、页脚、独立页码、广告或推广块。
2. merge_groups：合并因分页/OCR而断开的相邻正文块；只能列连续块 ID。
3. heading_levels：把已有标题的 Markdown 层级调整到 1-6；不得把正文改成标题。
4. drop_reasons：为每个删除块给出简短原因。
宁可保留可疑正文，不要误删。返回 JSON 对象，不要返回 Markdown 或解释。"""


def _chunks(blocks: list[Block], max_chars: int = 12000, max_blocks: int = 80) -> Iterable[list[Block]]:
    chunk: list[Block] = []
    size = 0
    for block in blocks:
        addition = len(block.text) + len(block.table_html or "") + 100
        if chunk and (size + addition > max_chars or len(chunk) >= max_blocks):
            yield chunk
            chunk = []
            size = 0
        chunk.append(block)
        size += addition
    if chunk:
        yield chunk


def _extract_json(text: str) -> dict[str, object]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"AI 返回的清洗指令不是有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise PipelineError("AI 返回的清洗指令必须是 JSON 对象")
    return payload


def request_ai_operations(
    blocks: list[Block],
    config: AIConfig,
    logger: logging.Logger,
) -> dict[str, object]:
    """逐块组请求 AI，并合并操作；正文从不交给模型重写。"""

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    combined: dict[str, object] = {
        "drop_ids": [],
        "drop_reasons": {},
        "merge_groups": [],
        "heading_levels": {},
    }
    chunks = list(_chunks(blocks))
    for index, chunk in enumerate(chunks, start=1):
        logger.info("AI 清洗块组 %d/%d（%d 个内容块）", index, len(chunks), len(chunk))
        records = [
            {
                "id": block.block_id,
                "type": block.kind,
                "source_type": block.source_kind,
                "page": block.page + 1,
                "heading_level": block.heading_level,
                "text": block.text,
            }
            for block in chunk
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "blocks": records,
                        "output_schema": {
                            "drop_ids": ["block_id"],
                            "drop_reasons": {"block_id": "reason"},
                            "merge_groups": [["adjacent_block_id_1", "adjacent_block_id_2"]],
                            "heading_levels": {"heading_block_id": 2},
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        response = None
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                break
            except Exception as first_exc:
                logger.warning("AI JSON 请求第 %d 次失败，尝试兼容模式：%s", attempt, first_exc)
                try:
                    response = client.chat.completions.create(
                        model=config.model,
                        messages=messages,
                        temperature=0,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(attempt)
        if response is None:
            raise PipelineError(f"AI 清洗请求失败：{last_error}") from last_error
        content = response.choices[0].message.content or ""
        operation = _extract_json(content)
        for key in ("drop_ids", "merge_groups"):
            value = operation.get(key, [])
            if isinstance(value, list):
                combined[key].extend(value)  # type: ignore[union-attr]
        for key in ("drop_reasons", "heading_levels"):
            value = operation.get(key, {})
            if isinstance(value, dict):
                combined[key].update(value)  # type: ignore[union-attr]
    return combined
