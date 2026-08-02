#!/usr/bin/env python3
"""构建包含 SwiftUI、Python 3.12 与 MinerU 的独立 macOS App。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON_RUNTIME = Path(sys.base_prefix)
SITE_PACKAGES = PROJECT_ROOT / ".venv/lib/python3.12/site-packages"
APP_NAME = "PDF 转 Markdown.app"
EXECUTABLE_NAME = "PDFToMarkdown"
LEGACY_INSTALL_PATH = Path("/Applications") / APP_NAME


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def cleanup_old_app_copies(output_root: Path, final_app: Path) -> None:
    """Remove known old copies only after the new App has passed validation."""

    old_paths = [LEGACY_INSTALL_PATH]
    for path in old_paths:
        if path == final_app or not path.exists():
            continue
        print(f"清理旧版 App：{path}", flush=True)
        shutil.rmtree(path)

    for pattern in (".PDFToMarkdown.staging-*", ".PDFToMarkdown.backup-*"):
        for path in output_root.glob(pattern):
            if path == final_app:
                continue
            print(f"清理构建现场：{path}", flush=True)
            shutil.rmtree(path)


def verify_xcode_toolchain() -> None:
    """SwiftUI macro plugins are supplied by full Xcode, not CLT alone."""

    developer_dir = os.environ.get("DEVELOPER_DIR", "")
    selected = subprocess.run(
        ["xcode-select", "-p"], capture_output=True, text=True, check=False
    ).stdout.strip()
    active = developer_dir or selected
    xcodebuild = shutil.which("xcodebuild")
    if not xcodebuild or active.endswith("/CommandLineTools"):
        raise RuntimeError(
            "构建 macOS SwiftUI App 需要完整 Xcode（当前仅检测到 CommandLineTools）。"
            "请安装 Xcode，或设置 DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer 后重试。"
        )


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
        if name in {
            "_editable_impl_pdf_to_markdown.pth",
            "_virtualenv.pth",
            "_virtualenv.py",
        }:
            ignored.add(name)
    return ignored


def create_icon(source: Path, resources: Path, work_dir: Path) -> None:
    del work_dir
    image = Image.open(source).convert("RGBA")
    image.save(
        resources / "AppIcon.icns",
        format="ICNS",
        sizes=[
            (16, 16),
            (32, 32),
            (64, 64),
            (128, 128),
            (256, 256),
            (512, 512),
            (1024, 1024),
        ],
    )


def build(output_root: Path, python_runtime: Path) -> Path:
    verify_xcode_toolchain()
    if not python_runtime.joinpath("bin/python3.12").is_file():
        raise RuntimeError(f"找不到独立 Python 3.12：{python_runtime}")
    if not SITE_PACKAGES.is_dir():
        raise RuntimeError(f"找不到项目依赖：{SITE_PACKAGES}")

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".PDFToMarkdown.staging-{uuid.uuid4().hex[:8]}"
    app = staging / APP_NAME
    contents = app / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    runtime_dir = resources / "runtime"
    bundled_python = runtime_dir / "python"
    bundled_site_packages = runtime_dir / "site-packages"
    module_cache = Path("/private/tmp/pdf2md-swift-module-cache")
    module_cache.mkdir(parents=True, exist_ok=True)
    macos_dir.mkdir(parents=True)
    resources.mkdir(parents=True)

    print("编译 SwiftUI…", flush=True)
    swift_sources = sorted((PROJECT_ROOT / "macos/Sources").glob("*.swift"))
    run(
        [
            "swiftc",
            "-parse-as-library",
            "-O",
            "-module-cache-path",
            str(module_cache),
            *map(str, swift_sources),
            "-o",
            str(macos_dir / EXECUTABLE_NAME),
        ],
        cwd=PROJECT_ROOT,
    )
    shutil.copy2(PROJECT_ROOT / "macos/Resources/Info.plist", contents / "Info.plist")

    print("生成 App 图标…", flush=True)
    create_icon(PROJECT_ROOT / "macos/Resources/AppIcon-Source.png", resources, staging)

    print("复制独立 Python 3.12…", flush=True)
    shutil.copytree(
        python_runtime,
        bundled_python,
        symlinks=True,
        ignore=copy_ignore,
    )

    print("复制 MinerU 与 Python 依赖（约 1.3GB）…", flush=True)
    shutil.copytree(
        SITE_PACKAGES,
        bundled_site_packages,
        symlinks=True,
        ignore=copy_ignore,
    )

    print("写入项目后端源码…", flush=True)
    packaged_project = bundled_site_packages / "pdf_to_md"
    if packaged_project.exists():
        shutil.rmtree(packaged_project)
    shutil.copytree(
        PROJECT_ROOT / "src/pdf_to_md",
        packaged_project,
        ignore=copy_ignore,
    )

    build_info = {
        "app_version": "0.1.0",
        "bundle_id": "com.local.PDFToMarkdown",
        "python": "3.12.13",
        "architecture": "arm64",
        "mineru": "3.4.4",
        "built_at": datetime.now().astimezone().isoformat(),
        "models_bundled": False,
        "model_source": "modelscope",
    }
    (resources / "BuildInfo.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("清理扩展属性并执行本地签名…", flush=True)
    run(["xattr", "-cr", str(app)])
    run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    run(["plutil", "-lint", str(contents / "Info.plist")])

    final_app = output_root / APP_NAME
    backup: Path | None = None
    if final_app.exists():
        backup = output_root / f".PDFToMarkdown.backup-{uuid.uuid4().hex[:8]}.app"
        final_app.rename(backup)
    try:
        app.rename(final_app)
    except Exception:
        if backup and backup.exists() and not final_app.exists():
            backup.rename(final_app)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if backup:
        shutil.rmtree(backup)
    cleanup_old_app_copies(output_root, final_app)
    return final_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="App 输出目录，默认 dist/",
    )
    parser.add_argument(
        "--python-runtime",
        type=Path,
        default=DEFAULT_PYTHON_RUNTIME,
        help="独立 Python 3.12 运行时目录，默认使用当前解释器的基础运行时",
    )
    args = parser.parse_args()
    try:
        result = build(args.output.resolve(), args.python_runtime.resolve())
    except Exception as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    print(f"构建完成：{result}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
