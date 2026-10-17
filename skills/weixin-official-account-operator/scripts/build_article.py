#!/usr/bin/env python3
"""公众号成稿一键流水线（阶段 A，纯本地，无外部副作用）：体检 → 按选题设计排版 → 渲染 HTML → HTML 合规体检。

一条命令替代“先 lint、再 suggest、再 render”三步；ERROR 未清零时不渲染，直接返回退出码 1。
其余参数（--design / --hint / --mood / --palette / --primary / --accent / --set / --numbered / --density /
--save-design / --no-caption）原样传给 render_layout.py；不给时按选题自动设计。

用法：
  python3 scripts/build_article.py 正文.md -o out.html [--design 方案.json] [--palette autumn | --primary #RRGGBB]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALUE_FLAGS = ("design", "hint", "mood", "palette", "primary", "accent", "set", "save-design")


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(HERE / script), *args]).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="体检 + 渲染一键流水线（本地，只写 -o 指定文件）")
    ap.add_argument("article", type=Path, help="Markdown 正文文件")
    ap.add_argument("-o", "--out", type=Path, required=True, help="HTML 输出路径")
    for flag in VALUE_FLAGS:
        ap.add_argument(f"--{flag}")
    ap.add_argument("--numbered", action="store_true")
    ap.add_argument("--no-caption", action="store_true")
    ap.add_argument("--density", choices=["large", "standard", "compact"])
    args = ap.parse_args()

    if not args.article.is_file():
        print(f"文件不存在：{args.article}", file=sys.stderr)
        return 2

    if run("lint_article.py", str(args.article), "--strict") != 0:
        print("\n体检存在 ERROR，已停止渲染；按“怎么改”修完后重跑。", file=sys.stderr)
        return 1

    render = [str(args.article), "-o", str(args.out)]
    for flag in VALUE_FLAGS + ("density",):
        value = getattr(args, flag.replace("-", "_"))
        if value:
            render += [f"--{flag}", value]
    for flag in ("numbered", "no_caption"):
        if getattr(args, flag):
            render.append("--" + flag.replace("_", "-"))
    if run("render_layout.py", *render) != 0:
        return 1
    # 含 :::html 手写组件时尤其需要：检查渲染结果能否安全进入微信
    return run("check_html.py", str(args.out), "--strict")


if __name__ == "__main__":
    sys.exit(main())
