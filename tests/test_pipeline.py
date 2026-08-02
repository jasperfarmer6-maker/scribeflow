from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from pdf_to_md.pipeline import (
    _mineru_processing_window_size,
    _mineru_timeout_seconds,
    _segment_ranges,
    run_pipeline,
)
from pdf_to_md.models import PipelineConfig


class MinerUTimeoutTests(unittest.TestCase):
    def test_segment_ranges_cover_every_page(self) -> None:
        self.assertEqual([(0, 16), (16, 32), (32, 37)], _segment_ranges(37, 16))
        self.assertEqual([(0, 1)], _segment_ranges(1, 16))

    @patch("pdf_to_md.pipeline._pdf_page_count", return_value=10)
    def test_short_pdf_uses_four_hour_minimum(self, _page_count) -> None:
        timeout, pages, overridden = _mineru_timeout_seconds(Path("short.pdf"), {})

        self.assertEqual(4 * 60 * 60, timeout)
        self.assertEqual(10, pages)
        self.assertFalse(overridden)

    @patch("pdf_to_md.pipeline._pdf_page_count", return_value=294)
    def test_thick_pdf_scales_timeout_by_page_count(self, _page_count) -> None:
        timeout, pages, overridden = _mineru_timeout_seconds(Path("thick.pdf"), {})

        self.assertEqual(294 * 60, timeout)
        self.assertEqual(294, pages)
        self.assertFalse(overridden)

    @patch("pdf_to_md.pipeline._pdf_page_count", return_value=2000)
    def test_timeout_is_capped_at_twenty_four_hours(self, _page_count) -> None:
        timeout, _, _ = _mineru_timeout_seconds(Path("huge.pdf"), {})

        self.assertEqual(24 * 60 * 60, timeout)

    @patch("pdf_to_md.pipeline._pdf_page_count", return_value=294)
    def test_valid_environment_override_is_preserved(self, _page_count) -> None:
        timeout, pages, overridden = _mineru_timeout_seconds(
            Path("thick.pdf"),
            {"MINERU_TASK_RESULT_TIMEOUT_SECONDS": "28800.5"},
        )

        self.assertEqual(28801, timeout)
        self.assertEqual(294, pages)
        self.assertTrue(overridden)


class ResumablePipelineTests(unittest.TestCase):
    def test_pipeline_resumes_after_failed_segment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            writer = PdfWriter()
            for _ in range(5):
                writer.add_blank_page(width=300, height=400)
            with source.open("wb") as stream:
                writer.write(stream)
            output = root / "book-Markdown"
            calls: list[str] = []
            failed_once = False

            def fake_mineru(config, raw_dir, logger, input_pdf=None):
                assert input_pdf is not None
                calls.append(input_pdf.name)
                nonlocal failed_once
                if not failed_once and len(calls) == 2:
                    failed_once = True
                    raise RuntimeError("simulated segment failure")
                result = raw_dir / input_pdf.stem / "ocr"
                result.mkdir(parents=True, exist_ok=True)
                page_count = len(PdfReader(input_pdf).pages)
                payload = [
                    {"type": "text", "text": f"正文第 {index + 1} 页", "page_idx": index}
                    for index in range(page_count)
                ]
                (result / f"{input_pdf.stem}_content_list.json").write_text(json.dumps(payload), encoding="utf-8")
                return {"page_count": page_count}

            config = PipelineConfig(input_pdf=source, output_dir=output, use_ai=False, segment_pages=2)
            with patch("pdf_to_md.pipeline._run_mineru", side_effect=fake_mineru):
                with self.assertRaises(Exception):
                    run_pipeline(config)
                self.assertEqual(["chunk-001.pdf", "chunk-002.pdf"], calls)
                calls.clear()
                resumed = PipelineConfig(input_pdf=source, output_dir=output, use_ai=False, segment_pages=2, resume=True)
                result = run_pipeline(resumed)

            self.assertEqual(output.resolve(), result)
            self.assertEqual(["chunk-002.pdf", "chunk-003.pdf"], calls)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(5, manifest["page_count"])
            self.assertEqual(5, manifest["completed_pages"])
            self.assertEqual(3, manifest["segment_count"])


class MinerUProcessingWindowTests(unittest.TestCase):
    def test_thick_pdf_uses_sixteen_page_window(self) -> None:
        window, overridden = _mineru_processing_window_size(294, {})

        self.assertEqual(16, window)
        self.assertFalse(overridden)

    def test_medium_pdf_uses_thirty_two_page_window(self) -> None:
        window, overridden = _mineru_processing_window_size(100, {})

        self.assertEqual(32, window)
        self.assertFalse(overridden)

    def test_short_pdf_keeps_default_window(self) -> None:
        window, overridden = _mineru_processing_window_size(50, {})

        self.assertEqual(64, window)
        self.assertFalse(overridden)

    def test_valid_window_environment_override_is_preserved(self) -> None:
        window, overridden = _mineru_processing_window_size(
            294,
            {"MINERU_PROCESSING_WINDOW_SIZE": "8"},
        )

        self.assertEqual(8, window)
        self.assertTrue(overridden)


if __name__ == "__main__":
    unittest.main()
