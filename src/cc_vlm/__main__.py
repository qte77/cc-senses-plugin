"""cc_vlm CLI entry point — capture screen and describe via in-process VLM.

Usage:
    python -m cc_vlm                         # capture, describe with config template
    python -m cc_vlm --template terminal     # override template
    python -m cc_vlm --no-cache              # bypass the frame-hash cache
    python -m cc_vlm --save-only             # capture + save path, no VLM call

Exit codes:
    0  success (description printed to stdout)
    1  VLM engine not available or returned an error
    2  bad arguments (handled by argparse)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from cc_vlm.cache import DescribeCache, describe_with_cache
from cc_vlm.capture import ScreenCapture
from cc_vlm.config import VLMConfig, load_vlm_config
from cc_vlm.engine import resolve_vlm_engine
from cc_vlm.processor import resize_for_vlm, save_jpeg
from cc_vlm.templates import PROMPT_TEMPLATES, get_template


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc_vlm",
        description="Capture and describe screen content via an in-process VLM.",
    )
    parser.add_argument(
        "--template",
        choices=list(PROMPT_TEMPLATES),
        help="Override the prompt template (default: from config)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the frame-hash cache and always call the VLM",
    )
    parser.add_argument(
        "--save-only",
        action="store_true",
        help="Capture + save JPEG, print the path, do not call the VLM",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor index to capture (default 1 = primary)",
    )
    parser.add_argument(
        "--image-file",
        type=Path,
        default=None,
        help=(
            "Use this pre-captured image file instead of capturing the screen. "
            "Useful for describing saved screenshots, headless test runs, or "
            "environments where mss cannot access a display."
        ),
    )
    return parser


def _capture_and_save(config: VLMConfig, monitor: int) -> Path:
    capture = ScreenCapture()
    img = capture.grab(monitor=monitor)
    img = resize_for_vlm(img, max_edge=config.max_dimension)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        dest = Path(tmp.name)
    save_jpeg(img, dest, quality=config.jpeg_quality)
    return dest


def _resolve_image_path(args: argparse.Namespace, config: VLMConfig) -> Path | None:
    """Return the image path to use, or None if an error was already printed."""
    if args.image_file is not None:
        if not args.image_file.is_file():
            print(
                f"cc_vlm: --image-file not found: {args.image_file}",
                file=sys.stderr,
            )
            return None
        return args.image_file
    try:
        return _capture_and_save(config, monitor=args.monitor)
    except Exception as exc:  # noqa: BLE001
        # Reason: screen capture can fail for many reasons (no display, no
        # permission, driver error, Wayland vs X11 mismatch). We catch
        # broadly here so the fallback hint always reaches the user.
        print(f"cc_vlm: screen capture failed: {exc}", file=sys.stderr)
        print(
            "cc_vlm: try --image-file PATH to describe a pre-captured image instead",
            file=sys.stderr,
        )
        return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_vlm_config()
    template_name = args.template or config.template
    prompt = get_template(template_name)

    image_path = _resolve_image_path(args, config)
    if image_path is None:
        return 1

    if args.save_only:
        print(str(image_path))
        return 0

    try:
        engine = resolve_vlm_engine(
            config.engine,
            model_path=config.model_path,
            mmproj_path=config.mmproj_path,
            handler_name=config.handler_name,
            n_ctx=config.n_ctx,
            n_gpu_layers=config.n_gpu_layers,
            max_tokens=config.max_tokens,
            server_url=config.server_url,
            server_model_alias=config.server_model_alias,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"cc_vlm: {exc}", file=sys.stderr)
        return 1

    try:
        if args.no_cache:
            text = engine.describe(image_path, prompt)
        else:
            cache = DescribeCache(max_size=config.cache_size)
            text = describe_with_cache(image_path, prompt, engine, cache)
    except RuntimeError as exc:
        print(f"cc_vlm: {exc}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
