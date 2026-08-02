from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pdf_to_md.ai_cleaner import request_ai_operations
from pdf_to_md.models import AIConfig, Block


class AICleanerTests(unittest.TestCase):
    @patch("pdf_to_md.ai_cleaner.OpenAI")
    def test_openai_compatible_json_operations_are_combined(self, openai_class: MagicMock) -> None:
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"drop_ids":["b2"],'
                            '"drop_reasons":{"b2":"广告"},'
                            '"merge_groups":[],'
                            '"heading_levels":{"b1":2}}'
                        )
                    )
                )
            ]
        )
        openai_class.return_value.chat.completions.create.return_value = completion
        blocks = [
            Block("b1", "heading", "章节", heading_level=1, source_kind="text"),
            Block("b2", "paragraph", "推广内容", source_kind="text"),
        ]
        result = request_ai_operations(
            blocks,
            AIConfig(model="test-model", api_key="test-key", base_url="http://localhost/v1"),
            logging.getLogger("test"),
        )
        self.assertEqual(["b2"], result["drop_ids"])
        self.assertEqual({"b1": 2}, result["heading_levels"])
        call = openai_class.return_value.chat.completions.create.call_args
        self.assertEqual("test-model", call.kwargs["model"])
        self.assertEqual({"type": "json_object"}, call.kwargs["response_format"])


if __name__ == "__main__":
    unittest.main()
