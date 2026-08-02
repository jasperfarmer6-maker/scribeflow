#!/usr/bin/env python3
"""Documentation contract checks; safe to run in CI or before a build."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REQUIRED = {
    "README.md", "architecture.md", "pipeline.md", "modules.md", "models.md",
    "configuration.md", "dependencies.md", "replaceability.md", "capabilities.md",
    "known-issues.md", "performance.md", "maintenance.md", "whitepaper.md",
    "CHANGELOG.md",
}


def main() -> int:
    errors: list[str] = []
    missing = sorted(name for name in REQUIRED if not (DOCS / name).is_file())
    errors.extend(f"缺少文档：docs/{name}" for name in missing)
    text = "\n".join(path.read_text(encoding="utf-8") for path in DOCS.glob("*.md") if path.is_file())
    for marker in ("已验证事实", "设计约束", "最后验证"):
        if marker not in text:
            errors.append(f"文档缺少元数据标记：{marker}")
    for name in ("PDF2MD_AI_MODEL", "PDF2MD_AI_API_KEY", "PDF2MD_AI_BASE_URL", "MINERU_TASK_RESULT_TIMEOUT_SECONDS", "MINERU_PROCESSING_WINDOW_SIZE"):
        if name not in (DOCS / "configuration.md").read_text(encoding="utf-8"):
            errors.append(f"配置未记录：{name}")
    help_result = subprocess.run(
        [sys.executable, "-m", "pdf_to_md.cli", "--help"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    help_text = help_result.stdout + help_result.stderr
    for option in ("--overwrite", "--no-ai", "--ai-model", "--model-source", "--chapter-level", "--mineru-bin"):
        if option not in help_text:
            errors.append(f"CLI 参数不可见或未记录：{option}")
    mermaid_count = text.count("```mermaid")
    if mermaid_count < 5:
        errors.append(f"流程图不足：当前 {mermaid_count} 个 Mermaid 图")
    for link in re.findall(r"\]\(([^)#]+\.md)\)", text):
        if not (DOCS / link).is_file():
            errors.append(f"失效文档链接：{link}")
    if errors:
        print("文档检查失败：")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"文档检查通过：{len(REQUIRED)} 个核心文档，{mermaid_count} 个 Mermaid 图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
