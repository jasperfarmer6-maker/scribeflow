from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pdf_to_md.gui_backend import main


class GUIBackendTests(unittest.TestCase):
    def test_progress_with_model_info_emits_redacted_model_event(self) -> None:
        from pdf_to_md.gui_backend import _progress

        stream = io.StringIO()
        with redirect_stdout(stream):
            with patch("sys.stdout", stream):
                _progress(
                    "ocr",
                    "OCR 已完成",
                    {
                        "model_info": {
                            "model_type": "ocr",
                            "model_name": "MinerU",
                            "model_path": "/Users/test/.cache/modelscope",
                            "api_key": "[已隐藏]",
                        }
                    },
                )
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(["model_info", "progress"], [event["type"] for event in events])
        self.assertNotIn("secret", stream.getvalue())
        self.assertEqual("[已隐藏]", events[0]["api_key"])

    @patch("pdf_to_md.gui_backend.run_pipeline")
    def test_json_lines_progress_and_result(self, run_pipeline_mock) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_pdf = root / "input.pdf"
            input_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            output = root / "output"
            output.mkdir()
            (output / "manifest.json").write_text(
                json.dumps(
                    {
                        "document": "document.md",
                        "markdown_count": 3,
                        "chapters": [{}, {}],
                        "log": "logs/pipeline.log",
                    }
                ),
                encoding="utf-8",
            )

            def fake_run(config, progress_callback, console_stream):
                progress_callback("reading", "正在读取 PDF", {})
                progress_callback("completed", "已完成", {"markdown_count": 3})
                return output

            run_pipeline_mock.side_effect = fake_run
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = main(
                    [
                        str(input_pdf),
                        "--output",
                        str(output),
                        "--no-ai",
                        "--overwrite",
                    ]
                )
            events = [json.loads(line) for line in stream.getvalue().splitlines()]

        self.assertEqual(0, exit_code)
        self.assertEqual(["progress", "progress", "result"], [event["type"] for event in events])
        self.assertEqual("reading", events[0]["status"])
        self.assertEqual(3, events[-1]["markdown_count"])


if __name__ == "__main__":
    unittest.main()
