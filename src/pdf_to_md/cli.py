"""命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .errors import PipelineError
from .models import AIConfig, PipelineConfig
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2md",
        description="扫描版 PDF -> 保真清洗 -> 按章节拆分 Markdown",
    )
    parser.add_argument("input_pdf", type=Path, help="输入 PDF 文件")
    parser.add_argument("-o", "--output", type=Path, required=True, help="最终输出目录")
    parser.add_argument("--overwrite", action="store_true", help="安全替换已有输出目录")
    parser.add_argument("--use-ai", action="store_true", help="启用在线 AI 清洗；默认关闭")
    parser.add_argument("--no-ai", action="store_true", help="兼容旧调用：关闭 AI")
    parser.add_argument("--ai-model", help="OpenAI 兼容模型名；也可用 PDF2MD_AI_MODEL")
    parser.add_argument("--ai-base-url", help="兼容接口地址；也可用 PDF2MD_AI_BASE_URL")
    parser.add_argument("--backend", default="pipeline", help="MinerU 后端，默认 pipeline")
    parser.add_argument("--method", default="ocr", choices=["auto", "txt", "ocr"])
    parser.add_argument("--lang", default="ch", help="OCR 语言，默认 ch")
    parser.add_argument(
        "--model-source",
        default="modelscope",
        choices=["modelscope", "huggingface", "local"],
    )
    parser.add_argument(
        "--chapter-level",
        type=int,
        choices=range(1, 7),
        metavar="1-6",
        help="章节切分标题级别；默认自动选择",
    )
    parser.add_argument("--discard-raw", action="store_true", help="成功后删除 MinerU 原始输出")
    parser.add_argument("--mineru-bin", help="自定义 MinerU CLI 路径")
    parser.add_argument("--segment-pages", type=int, default=16, help="每个 OCR 分段页数，默认 16")
    parser.add_argument("--resume", action="store_true", help="从匹配的失败现场或未完成暂存任务继续")
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
        result = run_pipeline(config)
    except PipelineError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(f"完成：{result}")
    print(f"完整 Markdown：{result / 'document.md'}")
    print(f"章节目录：{result / 'chapters'}")
    print(f"日志：{result / 'logs' / 'pipeline.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
