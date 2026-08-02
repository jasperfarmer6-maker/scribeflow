"""读取 MinerU 结构化输出、保真清洗并渲染 Markdown。"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterable
from pathlib import Path

from .errors import PipelineError
from .models import AuditEntry, Block


MARGINAL_KINDS = {
    "header",
    "footer",
    "page_header",
    "page_footer",
    "page_number",
}
PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:第\s*\d{1,4}\s*页|Page\s+\d{1,4}|[-—–]\s*\d{1,4}\s*[-—–]|\d{1,4}\s*/\s*\d{1,4})\s*$",
    re.IGNORECASE,
)
AD_RE = re.compile(
    r"(?:^|\s)(?:广告|ADVERTISEMENT|推广|赞助内容|商业合作|扫码关注|点击购买)(?:\s|[:：]|$)",
    re.IGNORECASE,
)
SENTENCE_END_RE = re.compile(r"[。！？.!?；;：:）)\]】”’\"']$")


def _join_text_parts(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_join_text_parts(item) for item in value)
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "title_content",
            "paragraph_content",
            "page_header_content",
            "page_footer_content",
            "page_number_content",
        ):
            if key in value:
                return _join_text_parts(value[key])
    return ""


def _caption_text(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return " ".join(part for part in (_join_text_parts(item).strip() for item in value) if part)
    return _join_text_parts(value).strip()


def load_mineru_blocks(content_list: Path) -> list[Block]:
    """读取 MinerU 的扁平 content_list JSON。"""

    try:
        payload = json.loads(content_list.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"无法读取 MinerU 结构化结果：{content_list}：{exc}") from exc
    if not isinstance(payload, list):
        raise PipelineError(f"MinerU 结构化结果格式异常（预期列表）：{content_list}")

    blocks: list[Block] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        source_kind = str(item.get("type", "unknown"))
        kind = "paragraph" if source_kind == "text" else source_kind
        text = str(item.get("text", "") or "")
        heading_level = item.get("text_level")
        if isinstance(heading_level, int):
            kind = "heading"
        else:
            heading_level = None

        table_html = item.get("table_body")
        image_path = item.get("img_path")
        caption = _caption_text(
            item.get("image_caption")
            or item.get("table_caption")
            or item.get("caption")
        )
        if not text and source_kind in MARGINAL_KINDS:
            text = _join_text_parts(item).strip()
        if not text and source_kind in {"equation", "interline_equation"}:
            text = str(item.get("latex", "") or item.get("text", ""))

        blocks.append(
            Block(
                block_id=f"b{index:06d}",
                kind=kind,
                text=text.strip(),
                heading_level=heading_level,
                page=int(item.get("page_idx", 0) or 0),
                bbox=list(item.get("bbox", []) or []),
                image_path=str(image_path) if image_path else None,
                table_html=str(table_html) if table_html else None,
                caption=caption,
                source_kind=source_kind,
            )
        )
    if not blocks:
        raise PipelineError(f"MinerU 没有返回可处理的内容块：{content_list}")
    return blocks


def deterministic_clean(blocks: list[Block]) -> tuple[list[Block], list[AuditEntry]]:
    """删除明确的边栏噪声和广告；不改写正文。"""

    cleaned: list[Block] = []
    audit: list[AuditEntry] = []
    for block in blocks:
        reason = ""
        if block.source_kind in MARGINAL_KINDS:
            reason = f"MinerU 标记为 {block.source_kind}"
        elif block.kind == "paragraph" and PAGE_NUMBER_RE.fullmatch(block.text):
            reason = "规则识别为独立页码"
        elif block.kind == "paragraph" and len(block.text) <= 160 and AD_RE.search(block.text):
            reason = "规则识别为广告或推广文字"
        if reason:
            audit.append(
                AuditEntry(
                    action="drop",
                    block_ids=[block.block_id],
                    reason=reason,
                    original_text=block.text,
                )
            )
            continue
        cleaned.append(block)
    return merge_obvious_breaks(cleaned, audit), audit


def merge_obvious_breaks(blocks: list[Block], audit: list[AuditEntry]) -> list[Block]:
    """仅修复确定的英文连字符断词和小写续行。"""

    result: list[Block] = []
    index = 0
    while index < len(blocks):
        current = blocks[index]
        if index + 1 < len(blocks):
            following = blocks[index + 1]
            can_merge = (
                current.kind == following.kind == "paragraph"
                and bool(current.text)
                and bool(following.text)
                and not SENTENCE_END_RE.search(current.text)
                and re.match(r"^[a-z]", following.text) is not None
            )
            if can_merge:
                merged = _merge_pair(current, following)
                audit.append(
                    AuditEntry(
                        action="merge",
                        block_ids=[current.block_id, following.block_id],
                        reason="确定性规则：英文小写续行或连字符断词",
                        original_text=f"{current.text}\\n{following.text}",
                    )
                )
                result.append(merged)
                index += 2
                continue
        result.append(current)
        index += 1
    return result


def _merge_pair(first: Block, second: Block) -> Block:
    if first.text.endswith("-") and re.match(r"^[A-Za-z]", second.text):
        joined = first.text[:-1] + second.text
    elif re.search(r"[\u3400-\u9fff]$", first.text) and re.match(r"^[\u3400-\u9fff]", second.text):
        joined = first.text + second.text
    else:
        joined = first.text.rstrip() + " " + second.text.lstrip()
    return Block(
        block_id=first.block_id,
        kind=first.kind,
        text=joined,
        heading_level=first.heading_level,
        page=first.page,
        bbox=first.bbox,
        image_path=first.image_path,
        table_html=first.table_html,
        caption=first.caption,
        source_kind=first.source_kind,
    )


def apply_ai_operations(
    blocks: list[Block],
    operations: dict[str, object],
    audit: list[AuditEntry],
) -> list[Block]:
    """应用经过验证的块级 AI 操作；AI 永远不能提供替换正文。"""

    known = {block.block_id: block for block in blocks}
    drop_ids = {
        item
        for item in operations.get("drop_ids", [])
        if isinstance(item, str) and item in known
    }
    reasons = operations.get("drop_reasons", {})
    if not isinstance(reasons, dict):
        reasons = {}
    for block_id in sorted(drop_ids):
        block = known[block_id]
        audit.append(
            AuditEntry(
                action="drop",
                block_ids=[block_id],
                reason=f"AI 分类：{str(reasons.get(block_id, '广告或页面噪声'))}",
                original_text=block.text,
            )
        )

    heading_levels = operations.get("heading_levels", {})
    if not isinstance(heading_levels, dict):
        heading_levels = {}
    for block_id, level in heading_levels.items():
        if (
            block_id in known
            and known[block_id].is_heading
            and isinstance(level, int)
            and 1 <= level <= 6
            and level != known[block_id].heading_level
        ):
            old_level = known[block_id].heading_level
            known[block_id].heading_level = level
            audit.append(
                AuditEntry(
                    action="heading_level",
                    block_ids=[block_id],
                    reason=f"AI 调整标题层级：{old_level} -> {level}",
                    original_text=known[block_id].text,
                )
            )

    remaining = [block for block in blocks if block.block_id not in drop_ids]
    positions = {block.block_id: idx for idx, block in enumerate(remaining)}
    merge_groups = operations.get("merge_groups", [])
    valid_groups: dict[str, list[str]] = {}
    occupied: set[str] = set()
    if isinstance(merge_groups, list):
        for raw_group in merge_groups:
            if not isinstance(raw_group, list) or len(raw_group) < 2:
                continue
            group = [item for item in raw_group if isinstance(item, str) and item in positions]
            indexes = [positions[item] for item in group]
            if (
                len(group) == len(raw_group)
                and indexes == list(range(indexes[0], indexes[0] + len(indexes)))
                and all(known[item].kind == "paragraph" for item in group)
                and not occupied.intersection(group)
            ):
                valid_groups[group[0]] = group
                occupied.update(group)

    merged: list[Block] = []
    skip: set[str] = set()
    for block in remaining:
        if block.block_id in skip:
            continue
        group = valid_groups.get(block.block_id)
        if not group:
            merged.append(block)
            continue
        combined = known[group[0]]
        original_lines = [combined.text]
        for block_id in group[1:]:
            original_lines.append(known[block_id].text)
            combined = _merge_pair(combined, known[block_id])
            skip.add(block_id)
        merged.append(combined)
        audit.append(
            AuditEntry(
                action="merge",
                block_ids=group,
                reason="AI 判定为同一句或同一段的跨块断裂",
                original_text="\\n".join(original_lines),
            )
        )
    return merged


def copy_assets(
    blocks: Iterable[Block],
    mineru_dir: Path,
    assets_dir: Path,
    namespace: str = "",
) -> dict[str, str]:
    """复制 MinerU 图片，返回源相对路径到目标文件名的映射。"""

    mapping: dict[str, str] = {}
    assets_dir.mkdir(parents=True, exist_ok=True)
    for block in blocks:
        if not block.image_path:
            continue
        source = mineru_dir / block.image_path
        if not source.is_file():
            continue
        filename = f"{namespace}{source.name}"
        target = assets_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        logical_path = f"{namespace}{block.image_path}"
        mapping[logical_path] = filename
        block.image_path = logical_path
    return mapping


def render_markdown(
    blocks: Iterable[Block],
    asset_mapping: dict[str, str],
    asset_prefix: str,
) -> str:
    """将内容块渲染为 Markdown。"""

    parts: list[str] = []
    for block in blocks:
        rendered = ""
        if block.is_heading and block.text:
            level = max(1, min(6, int(block.heading_level or 1)))
            rendered = f"{'#' * level} {block.text}"
        elif block.kind == "paragraph" and block.text:
            rendered = block.text
        elif block.kind in {"equation", "interline_equation"} and block.text:
            rendered = f"$$\n{block.text}\n$$"
        elif block.kind == "table":
            caption = f"**{block.caption}**\n\n" if block.caption else ""
            if block.table_html:
                rendered = caption + block.table_html
            elif block.image_path in asset_mapping:
                filename = asset_mapping[block.image_path]
                rendered = caption + f"![表格]({asset_prefix}/{filename})"
        elif block.kind in {"image", "figure"} and block.image_path in asset_mapping:
            filename = asset_mapping[block.image_path]
            alt = block.caption or "图片"
            rendered = f"![{alt}]({asset_prefix}/{filename})"
            if block.caption:
                rendered += f"\n\n*{block.caption}*"
        elif block.text:
            rendered = block.text
        if rendered:
            parts.append(rendered.strip())
    return "\n\n".join(parts).strip() + "\n"


def choose_chapter_level(blocks: Iterable[Block], requested: int | None) -> int | None:
    if requested is not None:
        return requested
    counts: dict[int, int] = {}
    for block in blocks:
        if block.heading_level:
            counts[block.heading_level] = counts.get(block.heading_level, 0) + 1
    for level in sorted(counts):
        if counts[level] >= 2:
            return level
    return min(counts) if counts else None


def split_chapters(blocks: list[Block], level: int | None) -> list[tuple[str, list[Block]]]:
    """按指定标题级别切分；标题前内容作为前言。"""

    if level is None:
        return [("全文", blocks)]
    preamble: list[Block] = []
    chapters: list[tuple[str, list[Block]]] = []
    current_title: str | None = None
    current: list[Block] = []
    for block in blocks:
        if block.heading_level == level:
            if current_title is not None and current:
                chapters.append((current_title, current))
            current_title = block.text or "未命名章节"
            current = [block]
        elif current_title is None:
            preamble.append(block)
        else:
            current.append(block)
    if current_title is not None and current:
        chapters.append((current_title, current))
    if not chapters:
        return [("全文", blocks)]

    preamble_has_body = any(not block.is_heading for block in preamble)
    if preamble_has_body:
        chapters.insert(0, ("前言", preamble))
    elif preamble:
        first_title, first_blocks = chapters[0]
        chapters[0] = (first_title, [*preamble, *first_blocks])
    return chapters


def safe_slug(value: str, fallback: str = "chapter") -> str:
    value = re.sub(r"[^\w\u3400-\u9fff-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    return value[:60] or fallback
