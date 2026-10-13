#!/usr/bin/env python3
"""公众号成稿一键流水线（阶段 A，纯本地，无外部副作用）：体检 → 主题推荐 → 渲染 HTML → HTML 合规体检。

一条命令替代“先 lint、再 suggest、再 render”三步；ERROR 未清零时不渲染，直接返回退出码 1。
其余参数（--theme / --primary / --accent / --density / --no-caption）原样传给 render_theme.py。

用法：
  python3 scripts/build_article.py 正文.md -o out.html [--theme tech | --primary #RRGGBB]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(HERE / script), *args]).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="体检 + 渲染一键流水线（本地，只写 -o 指定文件）")
    ap.add_argument("article", type=Path, help="Markdown 正文文件")
    ap.add_argument("-o", "--out", type=Path, required=True, help="HTML 输出路径")
    ap.add_argument("--theme")
    ap.add_argument("--primary")
    ap.add_argument("--accent")
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
    for flag in ("theme", "primary", "accent", "density"):
        value = getattr(args, flag)
        if value:
            render += [f"--{flag}", value]
    if args.no_caption:
        render.append("--no-caption")
    if run("render_theme.py", *render) != 0:
        return 1
    # 含 :::html 手写组件时尤其需要：检查渲染结果能否安全进入微信
    return run("check_html.py", str(args.out), "--strict")


if __name__ == "__main__":
    sys.exit(main())
