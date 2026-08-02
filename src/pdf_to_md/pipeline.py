"""扫描版 PDF 到章节 Markdown 的可恢复分段流水线。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import math
import os
import resource
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from pypdf import PdfReader, PdfWriter

from .ai_cleaner import request_ai_operations
from .content import (
    apply_ai_operations,
    choose_chapter_level,
    copy_assets,
    deterministic_clean,
    load_mineru_blocks,
    render_markdown,
    safe_slug,
    split_chapters,
)
from .errors import PipelineError
from .models import AuditEntry, Block, PipelineConfig


ProgressCallback = Callable[[str, str, dict[str, object]], None]

_MINERU_TIMEOUT_ENV = "MINERU_TASK_RESULT_TIMEOUT_SECONDS"
_MINERU_WINDOW_ENV = "MINERU_PROCESSING_WINDOW_SIZE"
_MINERU_MIN_TIMEOUT_SECONDS = 4 * 60 * 60
_MINERU_SECONDS_PER_PAGE = 60
_MINERU_MAX_TIMEOUT_SECONDS = 24 * 60 * 60


def _emit_progress(callback: ProgressCallback | None, status: str, message: str, **details: object) -> None:
    if callback is None:
        return
    try:
        callback(status, message, details)
    except Exception:
        pass


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "[已隐藏的地址]"


def _model_cache_hint(model_source: str) -> dict[str, object]:
    candidates: list[str] = []
    home = Path.home()
    if model_source == "modelscope":
        candidates.extend([str(home / ".cache/modelscope"), str(home / ".cache/modelscope/hub")])
    elif model_source == "huggingface":
        candidates.append(str(home / ".cache/huggingface/hub"))
    existing = [path for path in candidates if Path(path).exists()]
    return {
        "model_path": existing[0] if existing else None,
        "model_path_status": "可定位缓存目录" if existing else "路径未由 MinerU 暴露",
        "model_path_candidates": candidates,
    }


def _setup_logger(log_file: Path, console_stream: TextIO | None = None) -> logging.Logger:
    logger = logging.getLogger(f"pdf_to_md.{uuid.uuid4().hex}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    console = logging.StreamHandler(console_stream or sys.stdout)
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


def _find_mineru_command(configured: str | None) -> list[str]:
    candidates = [configured, str(Path(sys.executable).with_name("mineru")), shutil.which("mineru")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return [candidate]
    if importlib.util.find_spec("mineru.cli.client") is not None:
        return [sys.executable, "-m", "mineru.cli.client"]
    raise PipelineError("找不到 MinerU CLI。请先安装 mineru[all]，或使用 --mineru-bin 指定路径。")


def _pdf_page_count(input_pdf: Path) -> int | None:
    try:
        return len(PdfReader(input_pdf, strict=False).pages)
    except Exception:
        return None


def _mineru_timeout_seconds(input_pdf: Path, environ: dict[str, str]) -> tuple[int, int | None, bool]:
    configured = environ.get(_MINERU_TIMEOUT_ENV)
    if configured:
        try:
            value = float(configured)
            if math.isfinite(value) and value >= 1:
                return math.ceil(value), _pdf_page_count(input_pdf), True
        except ValueError:
            pass
    page_count = _pdf_page_count(input_pdf)
    estimated = page_count * _MINERU_SECONDS_PER_PAGE if page_count is not None else _MINERU_MIN_TIMEOUT_SECONDS
    timeout = min(_MINERU_MAX_TIMEOUT_SECONDS, max(_MINERU_MIN_TIMEOUT_SECONDS, estimated))
    return timeout, page_count, False


def _mineru_processing_window_size(page_count: int | None, environ: dict[str, str]) -> tuple[int, bool]:
    configured = environ.get(_MINERU_WINDOW_ENV)
    if configured:
        try:
            value = int(configured)
            if value >= 1:
                return value, True
        except ValueError:
            pass
    if page_count is None:
        return 32, False
    if page_count >= 160:
        return 16, False
    if page_count >= 80:
        return 32, False
    return 64, False


def _run_mineru(
    config: PipelineConfig,
    raw_dir: Path,
    logger: logging.Logger,
    input_pdf: Path | None = None,
) -> dict[str, object]:
    source_pdf = input_pdf or config.input_pdf
    mineru_command = _find_mineru_command(config.mineru_bin)
    command = [
        *mineru_command, "-p", str(source_pdf), "-o", str(raw_dir), "-b", config.backend,
        "-m", config.method, "-l", config.language,
    ]
    env = os.environ.copy()
    env["MINERU_MODEL_SOURCE"] = config.model_source
    timeout_seconds, page_count, overridden = _mineru_timeout_seconds(source_pdf, env)
    env[_MINERU_TIMEOUT_ENV] = str(timeout_seconds)
    window_size, window_overridden = _mineru_processing_window_size(page_count, env)
    env[_MINERU_WINDOW_ENV] = str(window_size)
    logger.info("启动 MinerU：%s（%s 页）", source_pdf.name, page_count or "未知")
    logger.info("模型源：%s；超时：%.2f 小时；处理窗口：%d 页", config.model_source, timeout_seconds / 3600, window_size)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", env=env,
        )
    except OSError as exc:
        raise PipelineError(f"无法启动 MinerU：{exc}") from exc
    assert process.stdout is not None
    task_timed_out = False
    worker_unavailable = False
    for line in process.stdout:
        if "Timed out waiting for result of task" in line:
            task_timed_out = True
        if "Failed to query task status" in line and "502 Bad Gateway" in line:
            worker_unavailable = True
        logger.info("MinerU | %s", line.rstrip())
    return_code = process.wait()
    if return_code:
        if task_timed_out:
            raise PipelineError(f"MinerU 任务处理超时（{timeout_seconds / 3600:.2f} 小时）。")
        if worker_unavailable:
            raise PipelineError("MinerU OCR 工作服务返回 502，通常与内存压力有关。")
        raise PipelineError(f"MinerU 解析失败，退出码 {return_code}。详情见日志。")
    return {
        "model_type": "ocr", "model_name": "MinerU 内置 OCR/版面模型",
        "model_source": config.model_source, "mineru_cli_path": mineru_command[0],
        "python_path": sys.executable, "backend": config.backend, "method": config.method,
        "language": config.language, "page_count": page_count,
        "timeout_seconds": timeout_seconds, "timeout_overridden": overridden,
        "processing_window_size": window_size, "processing_window_overridden": window_overridden,
        **_model_cache_hint(config.model_source),
    }


def _locate_content_list(raw_dir: Path, stem: str) -> Path:
    candidates = [path for path in raw_dir.rglob("*_content_list.json") if not path.name.endswith("_content_list_v2.json")]
    if not candidates:
        raise PipelineError(f"MinerU 完成但没有生成 content_list JSON：{raw_dir}")
    candidates.sort(key=lambda path: (stem not in path.name, len(path.parts), str(path)))
    return candidates[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _segment_ranges(page_count: int, segment_pages: int) -> list[tuple[int, int]]:
    if page_count < 1:
        raise PipelineError("PDF 没有可处理的页面。")
    if segment_pages < 1:
        raise PipelineError("--segment-pages 必须是正整数。")
    return [(start, min(start + segment_pages, page_count)) for start in range(0, page_count, segment_pages)]


def _write_segment_pdf(source: Path, target: Path, start: int, end: int) -> None:
    if target.is_file():
        return
    reader = PdfReader(source, strict=False)
    writer = PdfWriter()
    for page in reader.pages[start:end]:
        writer.add_page(page)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(target)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _memory_megabytes() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return round(value / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)


def _find_resume_staging(output: Path, input_sha256: str) -> Path | None:
    candidates = list(output.parent.glob(f".{output.name}.staging-*"))
    candidates.extend(output.parent.glob(f"{output.name}.failed-*"))
    matches: list[Path] = []
    for candidate in candidates:
        try:
            payload = json.loads((candidate / "job_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("input_sha256") == input_sha256:
            matches.append(candidate)
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def _validate_page_coverage(blocks: list[Block], page_count: int) -> list[int]:
    pages = sorted({int(block.page) for block in blocks})
    invalid = [page for page in pages if page < 0 or page >= page_count]
    if invalid:
        raise PipelineError(f"OCR 返回了越界页码：{invalid[:8]}")
    page_set = set(pages)
    missing = [page for page in range(page_count) if page not in page_set]
    if missing:
        shown = ", ".join(str(page + 1) for page in missing[:12])
        raise PipelineError(f"OCR 页面覆盖不完整，缺少页面：{shown}")
    return pages


def _write_audit(path: Path, config: PipelineConfig, audit: list[AuditEntry], chapter_level: int | None) -> None:
    payload = {
        "input": str(config.input_pdf), "ai_enabled": config.use_ai,
        "ai_model": config.ai.model if config.ai else None, "chapter_level": chapter_level,
        "operations": [asdict(entry) for entry in audit],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _publish(staging: Path, output: Path, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise PipelineError(f"输出目录已存在：{output}。如需重跑，请加 --overwrite。")
    backup: Path | None = None
    if output.exists():
        backup = output.with_name(f".{output.name}.backup-{uuid.uuid4().hex[:8]}")
        output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        if backup and backup.exists() and not output.exists():
            backup.rename(output)
        raise
    if backup:
        shutil.rmtree(backup)


def run_pipeline(config: PipelineConfig, progress_callback: ProgressCallback | None = None, console_stream: TextIO | None = None) -> Path:
    """按固定页数顺序 OCR，并在每段完成后保存可恢复 checkpoint。"""
    _emit_progress(progress_callback, "reading", "正在读取 PDF")
    input_pdf = config.input_pdf.expanduser().resolve()
    output_dir = config.output_dir.expanduser().resolve()
    config.input_pdf, config.output_dir = input_pdf, output_dir
    if not input_pdf.is_file():
        raise PipelineError(f"输入 PDF 不存在：{input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise PipelineError(f"输入文件不是 PDF：{input_pdf}")
    if config.use_ai and config.ai is None:
        raise PipelineError("AI 清洗已启用，但缺少模型或 API 密钥配置。")
    page_count = _pdf_page_count(input_pdf)
    if page_count is None:
        raise PipelineError("无法读取 PDF 页数。")
    ranges = _segment_ranges(page_count, config.segment_pages)
    input_sha256 = _sha256(input_pdf)
    if output_dir.exists() and not config.overwrite:
        raise PipelineError(f"输出目录已存在：{output_dir}。如需重跑，请加 --overwrite。")
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    staging = _find_resume_staging(output_dir, input_sha256) if config.resume else None
    if staging is None:
        staging = output_dir.with_name(f".{output_dir.name}.staging-{uuid.uuid4().hex[:8]}")
    logs_dir = staging / "logs"
    raw_dir = staging / "raw" / "mineru"
    assets_dir = staging / "assets"
    chapters_dir = staging / "chapters"
    logs_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    logger = _setup_logger(logs_dir / "pipeline.log", console_stream)
    started = datetime.now()
    job_path = staging / "job_manifest.json"
    if job_path.exists():
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
            if job.get("input_sha256") != input_sha256 or job.get("page_count") != page_count:
                raise PipelineError("恢复现场与当前输入 PDF 不匹配。")
            if job.get("segment_pages") != config.segment_pages:
                raise PipelineError("恢复现场的分段大小不同，请使用原来的 --segment-pages。")
        except json.JSONDecodeError as exc:
            raise PipelineError(f"checkpoint 格式损坏：{job_path}") from exc
    else:
        job = {
            "status": "running", "input": str(input_pdf), "input_sha256": input_sha256,
            "page_count": page_count, "segment_pages": config.segment_pages,
            "segment_count": len(ranges),
            "segments": [
                {"index": index, "start_page": start + 1, "end_page": end, "status": "pending"}
                for index, (start, end) in enumerate(ranges, start=1)
            ],
        }
        _write_json_atomic(job_path, job)

    try:
        logger.info("输入：%s；页数：%d；分段：%d 页；恢复：%s", input_pdf, page_count, config.segment_pages, bool(job_path.exists()))
        _emit_progress(progress_callback, "ocr", "正在分段 OCR", page_count=page_count, segment_count=len(ranges))
        _emit_progress(progress_callback, "ocr", "OCR 模型准备中", model_info={
            "model_type": "ocr", "model_name": "MinerU 内置 OCR/版面模型",
            "model_source": config.model_source, "python_path": sys.executable,
            "backend": config.backend, "method": config.method, "language": config.language,
            "page_count": page_count, "segment_pages": config.segment_pages,
            **_model_cache_hint(config.model_source),
        })
        all_blocks: list[Block] = []
        asset_mapping: dict[str, str] = {}
        ocr_diagnostics: list[dict[str, object]] = []
        segment_dir = staging / "work" / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        for index, (start, end) in enumerate(ranges, start=1):
            record = job["segments"][index - 1]
            assert isinstance(record, dict)
            chunk_name = f"chunk-{index:03d}"
            chunk_pdf = segment_dir / f"{chunk_name}.pdf"
            raw_chunk = raw_dir / chunk_name
            _write_segment_pdf(input_pdf, chunk_pdf, start, end)
            segment_started = datetime.now()
            if record.get("status") != "completed":
                record.update({"status": "running", "started_at": segment_started.isoformat()})
                job["status"] = "running"
                _write_json_atomic(job_path, job)
                _emit_progress(progress_callback, "ocr", f"正在处理第 {index}/{len(ranges)} 段（第 {start + 1}-{end} 页）", segment=index, segment_count=len(ranges), start_page=start + 1, end_page=end)
                diagnostics = _run_mineru(config, raw_chunk, logger, chunk_pdf)
                record["diagnostics"] = diagnostics
            content_list = _locate_content_list(raw_chunk, chunk_name)
            chunk_result_dir = content_list.parent
            segment_blocks = load_mineru_blocks(content_list)
            for block_number, block in enumerate(segment_blocks, start=1):
                block.block_id = f"c{index:03d}-{block.block_id}"
                block.page += start
            asset_mapping.update(copy_assets(segment_blocks, chunk_result_dir, assets_dir, namespace=f"{chunk_name}/"))
            content_pages = sorted({block.page + 1 for block in segment_blocks})
            record.update({
                "status": "completed", "content_list": str(content_list.relative_to(staging)),
                "content_pages": content_pages, "block_count": len(segment_blocks),
                "duration_seconds": round((datetime.now() - segment_started).total_seconds(), 2),
                "max_rss_mb": _memory_megabytes(), "finished_at": datetime.now().isoformat(),
            })
            job["completed_pages"] = sum(item["end_page"] - item["start_page"] + 1 for item in job["segments"] if item.get("status") == "completed")
            _write_json_atomic(job_path, job)
            all_blocks.extend(segment_blocks)
            if isinstance(record.get("diagnostics"), dict):
                ocr_diagnostics.append(record["diagnostics"])
            _emit_progress(progress_callback, "ocr", f"第 {index}/{len(ranges)} 段完成（第 {start + 1}-{end} 页）", segment=index, segment_count=len(ranges), completed_pages=job["completed_pages"], page_count=page_count)

        _validate_page_coverage(all_blocks, page_count)
        all_blocks, audit = deterministic_clean(all_blocks)
        logger.info("读取 %d 个内容块，确定性清洗后剩余 %d 个", len(all_blocks) + len(audit), len(all_blocks))
        ai_diagnostics: dict[str, object] = {"model_type": "ai_cleaner", "enabled": config.use_ai}
        if config.use_ai:
            assert config.ai is not None
            _emit_progress(progress_callback, "cleaning", "正在使用 AI 清洗格式")
            ai_diagnostics.update({"model_name": config.ai.model, "base_url": _safe_url(config.ai.base_url), "temperature": 0, "chunk_max_chars": 12000, "chunk_max_blocks": 80})
            operations = request_ai_operations(all_blocks, config.ai, logger)
            all_blocks = apply_ai_operations(all_blocks, operations, audit)
        else:
            logger.info("已跳过在线 AI 清洗")

        _emit_progress(progress_callback, "writing", "正在生成 Markdown")
        document_md = render_markdown(all_blocks, asset_mapping, "assets")
        (staging / "document.md").write_text(document_md, encoding="utf-8")
        chapter_level = choose_chapter_level(all_blocks, config.chapter_level)
        chapters = split_chapters(all_blocks, chapter_level)
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapter_manifest: list[dict[str, object]] = []
        for index, (title, chapter_blocks) in enumerate(chapters, start=1):
            filename = f"{index:03d}-{safe_slug(title)}.md"
            (chapters_dir / filename).write_text(render_markdown(chapter_blocks, asset_mapping, "../assets"), encoding="utf-8")
            chapter_manifest.append({"index": index, "title": title, "file": f"chapters/{filename}"})
        _write_audit(staging / "cleaning_audit.json", config, audit, chapter_level)
        job.update({"status": "complete", "completed_pages": page_count, "completed_at": datetime.now().isoformat(), "max_rss_mb": _memory_megabytes()})
        _write_json_atomic(job_path, job)
        manifest = {
            "input": str(input_pdf), "input_sha256": input_sha256, "output": str(output_dir),
            "page_count": page_count, "completed_pages": page_count, "segment_pages": config.segment_pages,
            "segment_count": len(ranges), "segments": job["segments"],
            "mineru": {"backend": config.backend, "method": config.method, "language": config.language, "model_source": config.model_source},
            "ai": {"enabled": config.use_ai, "model": config.ai.model if config.ai else None},
            "diagnostics": {"ocr": ocr_diagnostics, "ai": ai_diagnostics, "max_rss_mb": _memory_megabytes(), "secrets_redacted": True},
            "document": "document.md", "chapters": chapter_manifest, "markdown_count": 1 + len(chapter_manifest),
            "assets": sorted(asset_mapping.values()), "audit": "cleaning_audit.json", "job": "job_manifest.json", "log": "logs/pipeline.log",
            "duration_seconds": round((datetime.now() - started).total_seconds(), 2),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if (staging / "work").exists():
            shutil.rmtree(staging / "work")
        if not config.keep_raw:
            shutil.rmtree(staging / "raw")
        _publish(staging, output_dir, config.overwrite)
        _emit_progress(progress_callback, "completed", "已完成", output_dir=str(output_dir), markdown_count=manifest["markdown_count"], chapter_count=len(chapter_manifest), duration_seconds=manifest["duration_seconds"])
        return output_dir
    except Exception as exc:
        job["status"] = "failed"
        job["last_error"] = str(exc)
        job["failed_at"] = datetime.now().isoformat()
        try:
            _write_json_atomic(job_path, job)
        except Exception:
            pass
        _emit_progress(progress_callback, "failed", "转换失败", error=str(exc), resume_available=True)
        logger.exception("流水线失败：%s", exc)
        failed = output_dir.with_name(f"{output_dir.name}.failed-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}")
        if staging.exists():
            try:
                staging.rename(failed)
                raise PipelineError(f"{exc} 失败现场已保留，可使用 --resume 继续：{failed}") from exc
            except OSError:
                pass
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(str(exc)) from exc
