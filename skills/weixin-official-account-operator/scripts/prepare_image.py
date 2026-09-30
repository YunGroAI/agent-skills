#!/usr/bin/env python3
"""公众号配图预处理：去水印 → 限制宽度 → 压缩到目标体积 → 合规自检。

用途：把 ImageGen 生成的图（或其它来源的图）处理成可交给
`weixin_oa_upload_content_image` / `weixin_oa_add_material` 的公网素材。

依赖 Pillow。若当前解释器没有 Pillow，先安装再执行：
  python3 -m pip install pillow
  python3 prepare_image.py ...

示例：
  prepare_image.py a.png b.png -o ./out
  prepare_image.py ./out --check-only          # 只做合规自检，不改动文件
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("缺少 Pillow：先 pip install pillow（见本文件顶部注释）")

MAX_WIDTH_DEFAULT = 1080
MAX_KB_DEFAULT = 200
QUALITY_RANGE = (85, 40)


def human_kb(num_bytes: int) -> float:
    return round(num_bytes / 1024, 1)


def magic_bytes(path: Path) -> str:
    with path.open("rb") as fh:
        return fh.read(4).hex()


def is_jpeg(path: Path) -> bool:
    return magic_bytes(path).startswith("ffd8ff")


def save_under_limit(im: Image.Image, target: Path, max_kb: int) -> tuple[int, int]:
    """二分选择 JPEG 质量，尽量贴近但不超过 max_kb。返回 (质量, 字节数)。"""
    lo, hi = QUALITY_RANGE
    best: tuple[int, bytes] | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=mid, optimize=True, progressive=True)
        size = buf.tell()
        if size <= max_kb * 1024:
            best = (mid, buf.getvalue())
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY_RANGE[1], optimize=True, progressive=True)
        best = (QUALITY_RANGE[1], buf.getvalue())
    target.write_bytes(best[1])
    return best[0], len(best[1])


def prepare(src: Path, outdir: Path, max_width: int, max_kb: int,
            crop_top: float, crop_bottom: float, do_crop: bool) -> dict:
    with Image.open(src) as raw:
        im = raw.convert("RGB")
    w, h = im.size
    if do_crop:
        im = im.crop((0, int(h * crop_top), w, int(h * (1 - crop_bottom))))
        w, h = im.size
    if w > max_width:
        im = im.resize((max_width, round(h * max_width / w)), Image.LANCZOS)
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f"{src.stem}_wx.jpg"
    quality, size = save_under_limit(im, target, max_kb)
    return {
        "file": str(target),
        "quality": quality,
        "kb": human_kb(size),
        "size": f"{im.width}x{im.height}",
        "jpeg": is_jpeg(target),
        "within_limit": size <= max_kb * 1024,
    }


def check(path: Path, max_kb: int, max_width: int) -> dict:
    size = path.stat().st_size
    with Image.open(path) as im:
        width = im.width
    return {
        "file": str(path),
        "kb": human_kb(size),
        "size": f"{width}x{Image.open(path).height}",
        "jpeg": is_jpeg(path),
        "within_limit": size <= max_kb * 1024 and width <= max_width,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号配图预处理与合规自检")
    ap.add_argument("inputs", nargs="+", type=Path, help="图片文件或目录")
    ap.add_argument("-o", "--outdir", type=Path, default=Path("./wx_images"),
                    help="输出目录，默认 ./wx_images")
    ap.add_argument("--width", type=int, default=MAX_WIDTH_DEFAULT, help="最大宽度，默认 1080")
    ap.add_argument("--max-kb", type=int, default=MAX_KB_DEFAULT, help="单图最大 KB，默认 200")
    ap.add_argument("--crop-top", type=float, default=0.02, help="裁掉顶部比例，默认 0.02")
    ap.add_argument("--crop-bottom", type=float, default=0.09, help="裁掉底部水印比例，默认 0.09")
    ap.add_argument("--no-crop", action="store_true", help="不裁剪，仅缩放压缩")
    ap.add_argument("--check-only", action="store_true", help="只自检，不生成新文件")
    args = ap.parse_args()

    files: list[Path] = []
    for item in args.inputs:
        if item.is_dir():
            files += sorted(p for p in item.iterdir() if p.is_file())
        elif item.is_file():
            files.append(item)
        else:
            print(f"跳过（不存在）: {item}", file=sys.stderr)

    if not files:
        print("没有可处理的图片", file=sys.stderr)
        return 1

    results = [
        check(p, args.max_kb, args.width) if args.check_only
        else prepare(p, args.outdir, args.width, args.max_kb,
                     args.crop_top, args.crop_bottom, not args.no_crop)
        for p in files
    ]

    print(f"{'文件':42s} {'尺寸':>10s} {'KB':>7s} {'JPEG':>5s} {'达标':>5s}")
    for item in results:
        name = os.path.basename(item["file"])[:42]
        print(f"{name:42s} {item['size']:>10s} {item['kb']:>7} "
              f"{'是' if item['jpeg'] else '否':>5s} {'是' if item['within_limit'] else '否':>5s}")

    failed = [r for r in results if not (r["jpeg"] and r["within_limit"])]
    if failed:
        print(f"\n{len(failed)} 张不达标，修正后再走上传通道", file=sys.stderr)
        return 1
    print(f"\n全部 {len(results)} 张达标，可部署为公网 HTTPS 地址后上传")
    return 0


if __name__ == "__main__":
    sys.exit(main())
