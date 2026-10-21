#!/usr/bin/env python3
"""公众号 HTML 合规体检：检查 Agent 手写或渲染出的正文 HTML 能否安全粘进微信编辑器 / 写入草稿。

检查项：禁用标签与事件属性、危险链接与 CSS、会被微信清掉的 class/id/<style>、定位与 Flex/Grid、
图片地址与 alt、正文字数与体积上限、强调色数量、过小字号、标签闭合。

用法：
  python3 scripts/check_html.py out.html
  python3 scripts/check_html.py out.html --final            # 入草稿前：图片必须已是微信图片地址
  python3 scripts/check_html.py out.html --strict           # 存在 ERROR 时退出码 1
  python3 scripts/check_html.py out.html --preview prev.html  # 生成 375px 手机宽度的本地预览页
  python3 scripts/check_html.py out.html --json

只做体检不改稿；预览页只写 --preview 指定的文件。仅依赖标准库。
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

MAX_CHARS = 19999
MAX_BYTES = 1024 * 1024
MAX_ACCENTS = 3          # 非灰色的色相家族数上限（同一色相的深浅算一种），超过即「色彩堆叠」
MIN_FONT_PX = 12

FORBIDDEN_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "textarea",
                  "select", "base", "link", "meta", "svg", "canvas", "frame", "frameset", "audio", "video"}
VOID_TAGS = {"img", "br", "hr", "wbr", "col", "source"}
WECHAT_IMG_HOSTS = ("mmbiz.qpic.cn", "mmbiz.qlogo.cn")
WECHAT_LINK_HOSTS = ("mp.weixin.qq.com",)

CSS_DANGER = re.compile(r"url\s*\(|@import|expression\s*\(|behavior\s*:|javascript:", re.I)
CSS_POSITION = re.compile(r"position\s*:\s*(absolute|fixed|sticky)", re.I)
CSS_LAYOUT = re.compile(r"display\s*:\s*(flex|inline-flex|grid|inline-grid)", re.I)
CSS_MOTION = re.compile(r"(animation|transition)\s*:", re.I)
CSS_FONT = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", re.I)
CSS_COLOR = re.compile(r"#(?:[0-9a-f]{6}|[0-9a-f]{3})\b|rgba?\([^)]*\)", re.I)


def normalize_color(raw: str) -> tuple[int, int, int] | None:
    raw = raw.lower()
    if raw.startswith("#"):
        h = raw[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    nums = re.findall(r"\d+(?:\.\d+)?", raw)
    if len(nums) >= 3:
        return tuple(min(255, int(float(n))) for n in nums[:3])  # type: ignore[return-value]
    return None


def is_neutral(rgb: tuple[int, int, int]) -> bool:
    """灰调色（HSL 饱和度 < 0.25，含黑白和暖灰正文色）与浅色底（亮度 ≥ 0.8）不算强调色。"""
    hi, lo = max(rgb), min(rgb)
    lightness = (hi + lo) / 510
    if hi == lo or lightness >= 0.8:
        return True
    saturation = (hi - lo) / (hi + lo if lightness <= 0.5 else 510 - hi - lo)
    return saturation < 0.25


def hue_families(colors: dict[str, tuple[int, int, int]]) -> list[list[str]]:
    """按色相把颜色归组：主色和它派生的深浅（色相差 ≤ 18°）算同一种颜色。"""
    groups: list[tuple[float, list[str]]] = []
    for name, (r, g, b) in sorted(colors.items()):
        hue = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[0] * 360
        for h, members in groups:
            if min(abs(h - hue), 360 - abs(h - hue)) <= 18:
                members.append(name)
                break
        else:
            groups.append((hue, [name]))
    return [members for _, members in groups]


class Checker(HTMLParser):
    def __init__(self, final: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.final = final
        self.issues: list[dict] = []
        self.stack: list[tuple[str, int]] = []
        self.text: list[str] = []
        self.colors: dict[str, tuple[int, int, int]] = {}
        self.images = 0
        self.skip_text = 0

    def add(self, level: str, kind: str, detail: str, fix: str) -> None:
        line = self.getpos()[0]
        self.issues.append({"level": level, "kind": kind, "line": line, "detail": detail, "fix": fix})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.check_tag(tag, attrs)
        if tag in FORBIDDEN_TAGS and tag in ("script", "style"):
            self.skip_text += 1
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.check_tag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip_text:
            self.skip_text -= 1
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for open_tag, line in self.stack[i + 1:]:
                    self.issues.append({"level": "WARN", "kind": "标签未闭合", "line": line,
                                        "detail": f"<{open_tag}> 在 </{tag}> 之前没有闭合",
                                        "fix": "补上闭合标签，避免微信编辑器把后续内容吞进同一个块"})
                del self.stack[i:]
                return
        self.add("WARN", "多余闭合", f"</{tag}> 没有对应的开始标签", "删掉多余的闭合标签")

    def handle_data(self, data: str) -> None:
        if not self.skip_text:
            self.text.append(data)

    def check_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in FORBIDDEN_TAGS:
            self.add("ERROR", "禁用标签", f"<{tag}>", "删掉；样式写成内联 style，音视频在公众号后台插入")
        for name in a:
            if name.startswith("on"):
                self.add("ERROR", "事件属性", f"<{tag} {name}=…>", "删掉所有事件属性")
        if "class" in a or "id" in a:
            self.add("WARN", "class/id 会被清掉", f"<{tag}> 带 class/id",
                     "微信不保留外部样式，把样式写进内联 style 后删掉 class/id")
        style = a.get("style", "")
        if style:
            self.check_style(tag, style)
        if tag == "a":
            href = a.get("href", "")
            if href and not re.match(r"^https?://", href, re.I):
                self.add("ERROR", "危险链接", f"href={href[:60]}", "只用 http(s) 链接")
            elif href and not any(h in href for h in WECHAT_LINK_HOSTS):
                self.add("WARN", "外链不可点", href[:80],
                         "正文外链在公众号里通常不可点击：放进「阅读原文」，或改为文字说明")
        if tag == "img":
            self.images += 1
            src = a.get("src") or a.get("data-src", "")
            if not a.get("alt"):
                self.add("WARN", "缺 alt", f"<img src={src[:60]}>", "补一句有意义的图片说明")
            if src.startswith("data:"):
                self.add("ERROR", "内嵌 base64 图", src[:40] + "…", "先上传本地图片拿微信图片地址再替换")
            elif not any(h in src for h in WECHAT_IMG_HOSTS):
                level = "ERROR" if self.final else "INFO"
                self.add(level, "非微信图片地址", src[:80],
                         "入草稿前按 publishing.md 上传，换成 mmbiz 图片地址；外部地址会被微信拦截或转存失败")

    def check_style(self, tag: str, style: str) -> None:
        if CSS_DANGER.search(style):
            self.add("ERROR", "危险 CSS", f"<{tag}> {CSS_DANGER.search(style).group(0)}",
                     "不用 url()、@import、expression、behavior；背景图改为 <img>")
        if CSS_POSITION.search(style):
            self.add("ERROR", "定位布局", f"<{tag}> {CSS_POSITION.search(style).group(0)}",
                     "微信会清掉定位，改成正常文档流")
        if CSS_LAYOUT.search(style):
            self.add("WARN", "Flex/Grid", f"<{tag}> {CSS_LAYOUT.search(style).group(0)}",
                     "部分客户端不支持，并排改用 inline-block + 百分比宽度")
        if CSS_MOTION.search(style):
            self.add("WARN", "动画", f"<{tag}> 含 animation/transition", "公众号会清掉动画，删掉")
        for size in CSS_FONT.findall(style):
            if float(size) < MIN_FONT_PX:
                self.add("WARN", "字号过小", f"<{tag}> font-size:{size}px", f"手机上不低于 {MIN_FONT_PX}px")
        for raw in CSS_COLOR.findall(style):
            rgb = normalize_color(raw)
            if rgb and not is_neutral(rgb):
                self.colors.setdefault("#%02x%02x%02x" % rgb, rgb)


def check(path: Path, final: bool) -> dict:
    source = path.read_text(encoding="utf-8")
    checker = Checker(final)
    checker.feed(source)
    checker.close()
    for tag, line in checker.stack:
        checker.issues.append({"level": "WARN", "kind": "标签未闭合", "line": line,
                               "detail": f"<{tag}> 到文件末尾仍未闭合", "fix": "补上闭合标签"})

    text = re.sub(r"\s+", "", "".join(checker.text))
    size = len(source.encode("utf-8"))
    if len(text) > MAX_CHARS:
        checker.issues.append({"level": "ERROR", "kind": "字数超限", "line": 0,
                               "detail": f"正文 {len(text)} 字", "fix": f"公众号正文上限 {MAX_CHARS} 字，拆成两篇"})
    if size >= MAX_BYTES:
        checker.issues.append({"level": "ERROR", "kind": "体积超限", "line": 0,
                               "detail": f"{size / 1024:.0f} KB", "fix": "正文 HTML 需小于 1MB：精简重复的内联样式"})
    families = hue_families(checker.colors)
    if len(families) > MAX_ACCENTS:
        checker.issues.append({"level": "WARN", "kind": "色彩堆叠", "line": 0,
                               "detail": f"{len(families)} 种色相：" + "；".join("、".join(f) for f in families),
                               "fix": "全文一个主强调色（可加一个浅底色），其余统一成主色或灰色"})
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    checker.issues.sort(key=lambda x: (order[x["level"]], x["line"]))
    return {"file": str(path), "chars": len(text), "bytes": size, "images": checker.images,
            "accent_colors": sorted(checker.colors), "issues": checker.issues}


PREVIEW = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公众号手机预览（本地）</title></head>
<body style="margin:0;background:#ededed;">
<div style="width:375px;margin:24px auto;background:#fff;padding:20px 0;box-shadow:0 2px 12px rgba(0,0,0,.08);
font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">
{body}
</div></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号 HTML 合规体检（本地，只读）")
    ap.add_argument("html", type=Path, help="正文 HTML 文件（片段或完整页面均可）")
    ap.add_argument("--final", action="store_true", help="入草稿前检查：非微信图片地址记为 ERROR")
    ap.add_argument("--strict", action="store_true", help="存在 ERROR 时退出码 1")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--preview", type=Path, help="生成 375px 手机宽度的本地预览页")
    args = ap.parse_args()

    if not args.html.is_file():
        print(f"文件不存在：{args.html}", file=sys.stderr)
        return 2

    report = check(args.html, args.final)
    errors = sum(1 for i in report["issues"] if i["level"] == "ERROR")

    if args.preview:
        body = args.html.read_text(encoding="utf-8")
        match = re.search(r"<body[^>]*>(.*)</body>", body, re.S | re.I)
        args.preview.write_text(PREVIEW.replace("{body}", match.group(1) if match else body), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['file']}：正文 {report['chars']} 字，{report['bytes'] / 1024:.1f} KB，"
              f"图片 {report['images']} 张，强调色 {', '.join(report['accent_colors']) or '无'}")
        if not report["issues"]:
            print("未发现问题。")
        for item in report["issues"]:
            where = f"第 {item['line']} 行 " if item["line"] else ""
            print(f"[{item['level']}] {item['kind']}：{where}{item['detail']}\n        怎么改：{item['fix']}")
        if args.preview:
            print(f"\n本地手机预览：{args.preview}（只是版式参考，以微信读回版本为准）")

    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    sys.exit(main())
