from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pdf_to_md.content import (
    apply_ai_operations,
    choose_chapter_level,
    copy_assets,
    deterministic_clean,
    load_mineru_blocks,
    render_markdown,
    safe_slug,
    split_chapters,
)
from pdf_to_md.models import AuditEntry, Block


class ContentTests(unittest.TestCase):
    def test_load_clean_and_render_without_rewriting(self) -> None:
        payload = [
            {
                "type": "header",
                "text": "某书固定页眉",
                "page_idx": 0,
                "bbox": [10, 10, 100, 20],
            },
            {
                "type": "text",
                "text": "第一章 原文标题",
                "text_level": 1,
                "page_idx": 0,
            },
            {"type": "text", "text": "正文保持原样。", "page_idx": 0},
            {"type": "text", "text": "广告：扫码关注", "page_idx": 0},
            {"type": "page_number", "text": "12", "page_idx": 0},
            {
                "type": "image",
                "img_path": "images/picture.jpg",
                "image_caption": ["原图说明"],
                "page_idx": 0,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book_content_list.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            blocks = load_mineru_blocks(path)

        cleaned, audit = deterministic_clean(blocks)
        markdown = render_markdown(
            cleaned,
            {"images/picture.jpg": "picture.jpg"},
            "assets",
        )
        self.assertIn("# 第一章 原文标题", markdown)
        self.assertIn("正文保持原样。", markdown)
        self.assertIn("![原图说明](assets/picture.jpg)", markdown)
        self.assertNotIn("固定页眉", markdown)
        self.assertNotIn("扫码关注", markdown)
        self.assertNotIn("\n12\n", markdown)
        self.assertEqual(3, len([item for item in audit if item.action == "drop"]))

    def test_ai_can_only_apply_valid_block_operations(self) -> None:
        blocks = [
            Block("b1", "heading", "第一章", heading_level=1, source_kind="text"),
            Block("b2", "paragraph", "这是断开的前半句", source_kind="text"),
            Block("b3", "paragraph", "后半句。", source_kind="text"),
            Block("b4", "paragraph", "赞助内容", source_kind="text"),
        ]
        audit: list[AuditEntry] = []
        operations = {
            "drop_ids": ["b4", "not-found"],
            "drop_reasons": {"b4": "广告"},
            "merge_groups": [["b2", "b3"], ["b1", "b2"]],
            "heading_levels": {"b1": 2, "b2": 1},
            "replacement_text": {"b2": "模型试图改写的文字"},
        }
        result = apply_ai_operations(blocks, operations, audit)
        self.assertEqual(["b1", "b2"], [block.block_id for block in result])
        self.assertEqual(2, result[0].heading_level)
        self.assertEqual("这是断开的前半句后半句。", result[1].text)
        self.assertNotIn("模型试图改写", result[1].text)
        self.assertTrue(any(item.action == "drop" and item.block_ids == ["b4"] for item in audit))

    def test_chapter_selection_and_links(self) -> None:
        blocks = [
            Block("b1", "heading", "书名", heading_level=1),
            Block("b2", "heading", "第一章", heading_level=2),
            Block("b3", "paragraph", "内容一。"),
            Block("b4", "heading", "第二章", heading_level=2),
            Block("b5", "image", image_path="images/x.jpg", caption="插图"),
        ]
        level = choose_chapter_level(blocks, None)
        chapters = split_chapters(blocks, level)
        self.assertEqual(2, level)
        self.assertEqual(["第一章", "第二章"], [title for title, _ in chapters])
        self.assertEqual("书名", chapters[0][1][0].text)
        markdown = render_markdown(chapters[-1][1], {"images/x.jpg": "x.jpg"}, "../assets")
        self.assertIn("![插图](../assets/x.jpg)", markdown)

    def test_safe_slug(self) -> None:
        self.assertEqual("第一章-开始", safe_slug("第一章：开始"))
        self.assertEqual("chapter", safe_slug("///"))

    def test_copy_assets_uses_stable_segment_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mineru" / "images"
            source.mkdir(parents=True)
            (source / "figure.jpg").write_bytes(b"jpg")
            target = root / "assets"
            block = Block("b1", "image", image_path="images/figure.jpg")
            mapping = copy_assets([block], root / "mineru", target, namespace="chunk-001/")
            self.assertEqual("chunk-001/figure.jpg", mapping["chunk-001/images/figure.jpg"])
            self.assertEqual("chunk-001/images/figure.jpg", block.image_path)
            self.assertTrue((target / "chunk-001/figure.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
