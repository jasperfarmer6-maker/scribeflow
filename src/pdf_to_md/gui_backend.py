"""供 macOS GUI 调用的 JSON Lines 后端入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .errors import PipelineError
from .models import AIConfig, PipelineConfig
from .pipeline import run_pipeline


def _emit_json(event_type: str, **payload: object) -> None:
    event = {"type": event_type, **payload}
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _progress(status: str, message: str, details: dict[str, object]) -> None:
    model_info = details.get("model_info")
    if isinstance(model_info, dict):
        _emit_json("model_info", **model_info)
    _emit_json("progress", status=status, message=message, **details)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PDF 转 Markdown macOS GUI 后端")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--use-ai", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--ai-model")
    parser.add_argument("--ai-base-url")
    parser.add_argument("--backend", default="pipeline")
    parser.add_argument("--method", default="ocr", choices=["auto", "txt", "ocr"])
    parser.add_argument("--lang", default="ch")
    parser.add_argument(
        "--model-source",
        default="modelscope",
        choices=["modelscope", "huggingface", "local"],
    )
    parser.add_argument("--chapter-level", type=int, choices=range(1, 7))
    parser.add_argument("--discard-raw", action="store_true")
    parser.add_argument("--mineru-bin")
    parser.add_argument("--segment-pages", type=int, default=16)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    use_ai = args.use_ai and not args.no_ai
    ai_config = None
    if use_ai:
        model = args.ai_model or os.getenv("PDF2MD_AI_MODEL") or os.getenv("OPENAI_MODEL")
        api_key = os.getenv("PDF2MD_AI_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = (
            args.ai_base_url
            or os.getenv("PDF2MD_AI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
        )
        if model and api_key:
            ai_config = AIConfig(model=model, api_key=api_key, base_url=base_url)

    config = PipelineConfig(
        input_pdf=args.input_pdf,
        output_dir=args.output,
        overwrite=args.overwrite,
        use_ai=use_ai,
        ai=ai_config,
        backend=args.backend,
        method=args.method,
        language=args.lang,
        model_source=args.model_source,
        chapter_level=args.chapter_level,
        keep_raw=not args.discard_raw,
        mineru_bin=args.mineru_bin,
        segment_pages=args.segment_pages,
        resume=args.resume,
    )
    try:
        result = run_pipeline(
            config,
            progress_callback=_progress,
            console_stream=sys.stderr,
        )
        manifest_path = result / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _emit_json(
            "result",
            success=True,
            output_dir=str(result),
            document=str(result / str(manifest["document"])),
            markdown_count=int(manifest.get("markdown_count", 0)),
            chapter_count=len(manifest.get("chapters", [])),
            log_path=str(result / str(manifest["log"])),
        )
        return 0
    except PipelineError as exc:
        _emit_json("error", success=False, message=str(exc))
        return 1
    except Exception as exc:
        _emit_json("error", success=False, message=f"未预期错误：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
