"""流水线内部数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Block:
    """MinerU 输出中的一个内容块。"""

    block_id: str
    kind: str
    text: str = ""
    heading_level: int | None = None
    page: int = 0
    bbox: list[float] = field(default_factory=list)
    image_path: str | None = None
    table_html: str | None = None
    caption: str = ""
    source_kind: str = ""

    @property
    def is_heading(self) -> bool:
        return self.heading_level is not None


@dataclass(slots=True)
class AuditEntry:
    """一次不会静默发生的清洗操作。"""

    action: str
    block_ids: list[str]
    reason: str
    original_text: str = ""


@dataclass(slots=True)
class AIConfig:
    """OpenAI 兼容接口配置。"""

    model: str
    api_key: str
    base_url: str | None = None


@dataclass(slots=True)
class PipelineConfig:
    """一次流水线运行配置。"""

    input_pdf: Path
    output_dir: Path
    overwrite: bool = False
    use_ai: bool = False
    ai: AIConfig | None = None
    backend: str = "pipeline"
    method: str = "ocr"
    language: str = "ch"
    model_source: str = "modelscope"
    chapter_level: int | None = None
    keep_raw: bool = True
    mineru_bin: str | None = None
    segment_pages: int = 16
    resume: bool = False
