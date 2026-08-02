from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf_to_md.cli import main


class CLITests(unittest.TestCase):
    def test_ai_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "input.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            with patch.dict(
                "os.environ",
                {
                    "PDF2MD_AI_MODEL": "",
                    "PDF2MD_AI_API_KEY": "",
                    "OPENAI_MODEL": "",
                    "OPENAI_API_KEY": "",
                },
                clear=False,
            ):
                with patch("pdf_to_md.cli.run_pipeline") as run_pipeline:
                    run_pipeline.side_effect = RuntimeError("stop after config")
                    with self.assertRaises(RuntimeError):
                        main([str(pdf), "-o", str(root / "output")])
        self.assertFalse(run_pipeline.call_args.args[0].use_ai)

    def test_use_ai_requires_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "input.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            with patch.dict("os.environ", {"PDF2MD_AI_MODEL": "", "PDF2MD_AI_API_KEY": "", "OPENAI_MODEL": "", "OPENAI_API_KEY": ""}, clear=False):
                code = main([str(pdf), "-o", str(root / "output"), "--use-ai"])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
