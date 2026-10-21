#!/usr/bin/env python3
"""按选题生成公众号封面（大字报）与正文信息图，纯本地，不联网。

用法：
  python3 scripts/make_visuals.py 配图.json -o wx_images [--design 方案.json] [--font 字体文件]
  python3 scripts/make_visuals.py --example > 配图.json      # 打印一份完整示例规格
  python3 scripts/make_visuals.py --list                     # 列出图形类型与图标

输出（都已是微信可直接上传的 JPEG，不需要再用 prepare_image.py 裁边）：
  cover_235.jpg   2.35:1 消息列表大图（1080 宽）
  cover_11.jpg    1:1 转发卡片 / 次条小图（取自画面正中，文字都在这个安全区里）
  <name>.jpg      每张正文信息图（1080 宽）

颜色取 --design 方案的主色/强调色（或规格里的 colors），封面、信息图和排版是同一套颜色。
需要 Pillow（python3 -m pip install pillow）和一个中文字体；找不到字体时用 --font 指定。
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("缺少 Pillow：先 python3 -m pip install pillow")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_image import save_under_limit  # noqa: E402

FIG_W, FIG_H = 1080, 640
COVER_W, COVER_H = 2350, 1000
SAFE_W = 900          # 1:1 裁切后仍完整的文字宽度
MAX_KB = 200

MOTIFS = ["building", "network", "chip", "shield", "magnifier", "chart", "doc", "globe"]
MOTIF_DESC = {
    "building": "政府/机构/监管方", "network": "模型/AI/平台/生态", "chip": "芯片/算力/硬件",
    "shield": "安全/合规/防护", "magnifier": "调查/审查/溯源", "chart": "数据/增长/财报",
    "doc": "政策文件/法规/合同", "globe": "全球/出海/国际关系",
}
FIG_TYPES = {
    "compare": "范围对照：覆盖什么 vs 不管什么、做 vs 不做、A vs B",
    "stack": "分层链路：从表层一路查到底层（最后一层高亮）",
    "shift": "转变：以前 → 现在（左右两个图标 + 底部标签）",
    "timeline": "时间线：几个节点按时间排开（最后一个高亮）",
    "bignum": "大数字：一个关键数字 + 一句解释",
}

EXAMPLE = {
    "anchor": "禁的不是 App，是模型血统：放大镜一路查到底层模型",
    "colors": {"primary": "#24477a", "accent": "#d65446"},
    "cover": {
        "kicker": "观点 · 中美 AI",
        "headline": "美国禁用",
        "highlight": "DeepSeek",
        "subline": "连“底下跑着它”的产品，也要拆",
        "motifs": ["building", "network"],
    },
    "figures": [
        {"name": "fig1_scope", "type": "compare",
         "left": {"title": "命令覆盖：联邦文职机构",
                  "icons": {"motif": "building", "labels": ["财政部", "国务院", "司法部 …"]},
                  "items": ["不得再采购 DeepSeek 产品与服务", "清除在用的 DeepSeek 产品",
                            "清除基于 DeepSeek 开发的第三方产品"],
                  "mark": "×", "emphasis": 2},
         "right": {"title": "命令没管的",
                   "items": [["国防部 / 情报系统", "不归国土安全部管，另有法律"],
                             ["美国企业和普通用户", "照常能用，App 没下架"],
                             ["实体清单", "DeepSeek 未被列入"]]}},
        {"name": "fig2_stack", "type": "stack", "label": "一路查到底",
         "layers": [["政府采购的系统", "界面上看不到 DeepSeek"],
                    ["供应商的第三方产品", "用 DeepSeek 技术开发"],
                    ["底层模型", "DeepSeek"]],
         "caption": "清除范围不看品牌，看底层模型"},
        {"name": "fig3_shift", "type": "shift",
         "before": {"motif": "chip", "title": "以前：管芯片", "desc": "卡算力"},
         "after": {"motif": "network", "title": "现在：查模型", "desc": "谁的模型能进谁的系统", "focus": True},
         "tags": ["采购禁令", "蒸馏指控", "国防法案"]},
    ],
}


# ---------- 颜色 ----------

def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def complement(rgb) -> tuple[int, int, int]:
    """主色和强调色相同时，造一个醒目的对比色给封面高亮块用。"""
    h, _, _ = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    r, g, b = colorsys.hls_to_rgb((h + 0.47) % 1, 0.47, 0.66)
    return round(r * 255), round(g * 255), round(b * 255)


class Palette:
    def __init__(self, primary: str, accent: str | None):
        p = hex_rgb(primary)
        a = hex_rgb(accent) if accent and accent.lower() != primary.lower() else complement(p)
        self.primary, self.accent = p, a
        self.dark = mix(p, (0, 0, 0), 0.55)
        self.paper = (246, 247, 249)
        self.ink = (32, 32, 32)
        self.muted = (108, 108, 108)
        self.line = mix(p, (255, 255, 255), 0.72)
        self.soft = mix(p, (255, 255, 255), 0.9)
        self.accent_soft = mix(a, (255, 255, 255), 0.86)
        self.white = (242, 245, 250)
        self.faint = mix(self.dark, (255, 255, 255), 0.22)


# ---------- 字体 ----------

def font_candidates() -> list[tuple[str, int]]:
    win = os.path.join(os.environ.get("WINDIR", ""), "Fonts")
    return [
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
        ("/System/Library/Fonts/PingFang.ttc", 0),
        ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
        ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", 0),
        ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ("/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc", 0),
        (os.path.join(win, "msyhbd.ttc"), 0),
        (os.path.join(win, "msyh.ttc"), 0),
        (os.path.join(win, "simhei.ttf"), 0),
    ]


def has_cjk(path: str, index: int) -> bool:
    try:
        f = ImageFont.truetype(path, 40, index=index)
    except OSError:
        return False
    box = f.getbbox("国")
    return box[2] - box[0] > 20


def find_font(explicit: str | None) -> tuple[str, int]:
    if explicit:
        if not has_cjk(explicit, 0):
            sys.exit(f"字体不可用或不含中文：{explicit}")
        return explicit, 0
    for path, index in font_candidates():
        if os.path.exists(path) and has_cjk(path, index):
            return path, index
    if shutil.which("fc-list"):
        out = subprocess.run(["fc-list", ":lang=zh", "file"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            path = line.split(":")[0].strip()
            if path and has_cjk(path, 0):
                return path, 0
    sys.exit("找不到中文字体：用 --font 指定一个支持中文的 .ttf/.ttc/.otf 文件")


class Fonts:
    def __init__(self, path: str, index: int):
        self.path, self.index = path, index
        self.cache: dict[int, ImageFont.FreeTypeFont] = {}

    def get(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self.cache:
            self.cache[size] = ImageFont.truetype(self.path, size, index=self.index)
        return self.cache[size]

    def fit(self, d: ImageDraw.ImageDraw, text: str, max_w: float, start: int, low: int = 18):
        size = start
        while size > low and d.textlength(text, font=self.get(size)) > max_w:
            size -= 2
        return self.get(size)


def wrap(d, text: str, font, max_w: float) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def text_c(d, cx: float, y: float, text: str, font, fill, stroke: int = 0):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=fill)


def text_h(font) -> int:
    box = font.getbbox("国A")
    return box[3] - box[1]


# ---------- 图标（只用基本几何，线条随尺寸缩放） ----------

def lw(s: float) -> int:
    return max(3, round(s / 45))


def m_building(d, cx, cy, s, color, accent, fill=None):
    w, h = s * 1.15, s
    x0, x1, base = cx - w / 2, cx + w / 2, cy + h / 2
    step = h * 0.06
    for i in range(3):
        inset = i * w * 0.03
        y = base - step * (i + 1)
        d.rectangle([x0 + inset, y, x1 - inset, y + step], outline=color, width=lw(s), fill=fill)
    top = base - step * 3
    col_top = top - h * 0.5
    ent = h * 0.08
    d.rectangle([x0 + w * 0.08, col_top - ent, x1 - w * 0.08, col_top], outline=color, width=lw(s), fill=fill)
    n, span = 6, w * 0.76
    cw = span / (n * 2 - 1)
    for i in range(n):
        c0 = x0 + w * 0.12 + i * 2 * cw
        d.rectangle([c0, col_top, c0 + cw, top], outline=color, width=lw(s), fill=fill)
    d.polygon([(x0 + w * 0.04, col_top - ent), (cx, col_top - ent - h * 0.22), (x1 - w * 0.04, col_top - ent)],
              outline=color, fill=fill, width=lw(s))


def m_network(d, cx, cy, s, color, accent, fill=None):
    rnd = random.Random(5)
    pts = [(cx, cy)]
    for ring, count in ((0.24, 6), (0.45, 9)):
        for i in range(count):
            a = 2 * math.pi * i / count + ring * 3
            pts.append((cx + math.cos(a) * s * ring + rnd.uniform(-s, s) * 0.03,
                        cy + math.sin(a) * s * ring + rnd.uniform(-s, s) * 0.03))
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            if math.dist(p, q) < s * 0.3:
                d.line([p, q], fill=mix(color, (255, 255, 255), 0.35), width=max(2, lw(s) - 1))
    r = s * 0.035
    for p in pts[1:]:
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)
    d.ellipse([cx - r * 1.6, cy - r * 1.6, cx + r * 1.6, cy + r * 1.6], fill=accent)


def m_chip(d, cx, cy, s, color, accent, fill=None):
    h = s * 0.32
    d.rounded_rectangle([cx - h, cy - h, cx + h, cy + h], radius=s * 0.04, outline=color, width=lw(s) + 1, fill=fill)
    d.rectangle([cx - h * 0.5, cy - h * 0.5, cx + h * 0.5, cy + h * 0.5], outline=color, width=lw(s))
    for k in range(5):
        o = -h * 0.72 + k * h * 0.36
        for a, b, c, e in ((cx + o, cy - h, cx + o, cy - h * 1.3), (cx + o, cy + h, cx + o, cy + h * 1.3),
                           (cx - h, cy + o, cx - h * 1.3, cy + o), (cx + h, cy + o, cx + h * 1.3, cy + o)):
            d.line([(a, b), (c, e)], fill=color, width=lw(s) + 1)


def m_shield(d, cx, cy, s, color, accent, fill=None):
    w, h = s * 0.7, s * 0.85
    top = cy - h / 2
    pts = [(cx - w / 2, top + h * 0.12), (cx, top), (cx + w / 2, top + h * 0.12)]
    for i in range(1, 11):
        t = i / 10
        pts.append((cx + w / 2 * (1 - t) ** 0.45, top + h * 0.12 + (h * 0.88) * t))
    for i in range(9, 0, -1):
        t = i / 10
        pts.append((cx - w / 2 * (1 - t) ** 0.45, top + h * 0.12 + (h * 0.88) * t))
    d.polygon(pts, outline=color, fill=fill, width=lw(s) + 1)
    d.line([(cx - w * 0.2, cy), (cx - w * 0.04, cy + h * 0.15), (cx + w * 0.24, cy - h * 0.15)],
           fill=accent, width=lw(s) * 2)


def m_magnifier(d, cx, cy, s, color, accent, fill=None):
    r = s * 0.3
    x, y = cx - s * 0.08, cy - s * 0.08
    d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=lw(s) + 2, fill=fill)
    d.line([(x + r * 0.72, y + r * 0.72), (x + r * 1.5, y + r * 1.5)], fill=color, width=lw(s) * 3)
    d.rectangle([x - s * 0.04, y - s * 0.04, x + s * 0.04, y + s * 0.04], fill=accent)


def m_chart(d, cx, cy, s, color, accent, fill=None):
    x0, y0, x1, y1 = cx - s * 0.42, cy - s * 0.38, cx + s * 0.42, cy + s * 0.38
    d.line([(x0, y0), (x0, y1), (x1, y1)], fill=color, width=lw(s) + 1)
    bw = s * 0.12
    for i, ratio in enumerate((0.3, 0.5, 0.45, 0.8)):
        bx = x0 + s * 0.08 + i * s * 0.2
        d.rectangle([bx, y1 - (y1 - y0) * ratio, bx + bw, y1 - lw(s)], fill=accent if i == 3 else color)


def m_doc(d, cx, cy, s, color, accent, fill=None):
    w, h = s * 0.62, s * 0.8
    x0, y0 = cx - w / 2, cy - h / 2
    fold = w * 0.25
    d.polygon([(x0, y0), (x0 + w - fold, y0), (x0 + w, y0 + fold), (x0 + w, y0 + h), (x0, y0 + h)],
              outline=color, fill=fill, width=lw(s) + 1)
    d.line([(x0 + w - fold, y0), (x0 + w - fold, y0 + fold), (x0 + w, y0 + fold)], fill=color, width=lw(s))
    for i in range(4):
        y = y0 + h * (0.3 + i * 0.13)
        d.line([(x0 + w * 0.15, y), (x0 + w * (0.85 if i < 3 else 0.5), y)], fill=color, width=lw(s))
    r = w * 0.14
    d.ellipse([x0 + w * 0.68 - r, y0 + h * 0.82 - r, x0 + w * 0.68 + r, y0 + h * 0.82 + r], outline=accent,
              width=lw(s) + 1)


def m_globe(d, cx, cy, s, color, accent, fill=None):
    r = s * 0.4
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=lw(s) + 1, fill=fill)
    for k in (0.45, 0.85):
        d.ellipse([cx - r * k, cy - r, cx + r * k, cy + r], outline=color, width=lw(s))
    for t in (-0.45, 0, 0.45):
        half = r * math.sqrt(1 - t * t)
        d.line([(cx - half, cy + r * t), (cx + half, cy + r * t)], fill=color, width=lw(s))
    d.ellipse([cx + r * 0.3 - s * 0.05, cy - r * 0.35 - s * 0.05, cx + r * 0.3 + s * 0.05, cy - r * 0.35 + s * 0.05],
              fill=accent)


DRAW = {"building": m_building, "network": m_network, "chip": m_chip, "shield": m_shield,
        "magnifier": m_magnifier, "chart": m_chart, "doc": m_doc, "globe": m_globe}


def motif(d, name: str, cx, cy, s, color, accent, fill=None):
    if name not in DRAW:
        sys.exit(f"未知图标「{name}」，可选：{'、'.join(MOTIFS)}")
    DRAW[name](d, cx, cy, s, color, accent, fill)


def grain(img: Image.Image, amount: int = 6, seed: int = 7) -> Image.Image:
    rnd = random.Random(seed)
    px = img.load()
    w, h = img.size
    for _ in range(w * h // 8):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]
        k = rnd.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + k)), max(0, min(255, g + k)), max(0, min(255, b + k)))
    return img


# ---------- 封面：大字报 ----------

def cover(spec: dict, pal: Palette, fonts: Fonts, out: Path) -> list[Path]:
    img = Image.new("RGB", (COVER_W, COVER_H), pal.dark)
    d = ImageDraw.Draw(img)
    top, bottom = mix(pal.dark, (0, 0, 0), 0.25), mix(pal.dark, pal.primary, 0.35)
    for y in range(COVER_H):
        d.line([(0, y), (COVER_W, y)], fill=mix(top, bottom, y / COVER_H))

    motifs = spec.get("motifs") or []
    for name, cx in zip(motifs[:2], (330, COVER_W - 330)):
        motif(d, name, cx, COVER_H / 2 + 20, 460, pal.faint, mix(pal.accent, pal.dark, 0.3))

    cx = COVER_W / 2
    blocks = []                                    # (kind, text, font, height)
    if spec.get("kicker"):
        f = fonts.fit(d, spec["kicker"], SAFE_W, 46, 28)
        blocks.append(("kicker", spec["kicker"], f, text_h(f) + 34))
    for line in str(spec["headline"]).split("\n"):
        f = fonts.fit(d, line, SAFE_W, 230 if spec.get("highlight") else 250, 90)
        blocks.append(("headline", line, f, text_h(f) + 46))
    if spec.get("highlight"):
        f = fonts.fit(d, spec["highlight"], SAFE_W - 110, 190, 80)
        blocks.append(("highlight", spec["highlight"], f, text_h(f) + 120))
    if spec.get("subline"):
        f = fonts.fit(d, spec["subline"], SAFE_W, 66, 34)
        blocks.append(("subline", spec["subline"], f, text_h(f) + 30))
    blocks.append(("rule", "", None, 12))
    total = sum(b[3] for b in blocks)
    y = (COVER_H - total) / 2
    for kind, text, f, h in blocks:
        if kind == "kicker":
            text_c(d, cx, y, text, f, pal.accent)
        elif kind == "headline":
            text_c(d, cx, y - f.getbbox(text)[1], text, f, pal.white, stroke=max(3, f.size // 32))
        elif kind == "highlight":
            tw = d.textlength(text, font=f) + 12
            d.rectangle([cx - tw / 2 - 50, y, cx + tw / 2 + 50, y + h - 30], fill=pal.accent)
            text_c(d, cx, y + 45 - f.getbbox(text)[1], text, f, (255, 255, 255), stroke=max(3, f.size // 34))
        elif kind == "subline":
            text_c(d, cx, y, text, f, mix(pal.white, pal.primary, 0.15), stroke=1)
        elif kind == "rule":
            d.rectangle([cx - SAFE_W / 2, y, cx + SAFE_W / 2, y + 8], fill=pal.accent)
        y += h
    grain(img, 8)

    wide = img.resize((1080, round(1080 * COVER_H / COVER_W)), Image.LANCZOS)
    side = COVER_H
    square = img.crop(((COVER_W - side) // 2, 0, (COVER_W + side) // 2, side)).resize((900, 900), Image.LANCZOS)
    paths = [out / "cover_235.jpg", out / "cover_11.jpg"]
    save_under_limit(wide, paths[0], MAX_KB)
    save_under_limit(square, paths[1], MAX_KB)
    return paths


# ---------- 正文信息图 ----------

def item_pair(item) -> tuple[str, str]:
    if isinstance(item, (list, tuple)):
        return str(item[0]), str(item[1]) if len(item) > 1 else ""
    return str(item), ""


def fig_compare(spec, pal, fonts, d):
    left, right = spec["left"], spec["right"]
    x0, x1, y0, y1 = 40, 600, 60, 600
    d.rounded_rectangle([x0, y0, x1, y1], radius=24, outline=pal.accent, width=5)
    d.rounded_rectangle([x0, y0, x1, y0 + 62], radius=24, fill=pal.accent)
    d.rectangle([x0, y0 + 32, x1, y0 + 62], fill=pal.accent)
    text_c(d, (x0 + x1) / 2, y0 + 12, left["title"], fonts.fit(d, left["title"], x1 - x0 - 40, 30), (255, 255, 255))
    y = y0 + 90
    icons = left.get("icons")
    if icons:
        labels = icons.get("labels") or ["", "", ""]
        step = (x1 - x0) / (len(labels) + 1)
        for i, label in enumerate(labels):
            cx = x0 + step * (i + 1)
            motif(d, icons.get("motif", "building"), cx, y + 75, min(120, step * 0.72), pal.primary, pal.accent,
                  fill=pal.soft)
            text_c(d, cx, y + 158, label, fonts.fit(d, label, step - 10, 24), pal.ink)
        y += 215
    items = left.get("items", [])
    mark, emph = left.get("mark", "•"), left.get("emphasis", -1)
    room = (y1 - 24 - y) / max(1, len(items))
    for i, item in enumerate(items):
        text = f"{mark} {item_pair(item)[0]}"
        f = fonts.fit(d, text, x1 - x0 - 70, min(28, int(room * 0.55)))
        hot = i == emph
        d.text((x0 + 38, y + (room - text_h(f)) / 2), text, font=f, fill=pal.accent if hot else pal.ink)
        y += room

    rx0, rx1 = 650, 1040
    d.text((rx0, 70), right["title"], font=fonts.fit(d, right["title"], rx1 - rx0, 30), fill=pal.primary)
    rows = right.get("items", [])
    gap = 26
    ch = min(124, (600 - 140 - gap * (len(rows) - 1)) / max(1, len(rows)))
    for k, row in enumerate(rows):
        title, desc = item_pair(row)
        cy = 140 + k * (ch + gap)
        d.rounded_rectangle([rx0, cy, rx1, cy + ch], radius=14, outline=pal.line, width=3, fill=(255, 255, 255))
        d.ellipse([rx0 + 22, cy + 22, rx0 + 50, cy + 50], outline=pal.primary, width=4)
        d.text((rx0 + 66, cy + 16), title, font=fonts.fit(d, title, rx1 - rx0 - 86, 26), fill=pal.ink)
        if desc:
            d.text((rx0 + 24, cy + ch * 0.58), desc, font=fonts.fit(d, desc, rx1 - rx0 - 44, 22), fill=pal.muted)


def fig_stack(spec, pal, fonts, d):
    layers = spec["layers"]
    n = len(layers)
    gap = 36
    lh = min(124, (520 - gap * (n - 1)) / n)
    top = 70 + (520 - (lh * n + gap * (n - 1))) / 2
    for i, layer in enumerate(layers):
        title, desc = item_pair(layer)
        last = i == n - 1
        inset = i * 36
        y = top + i * (lh + gap)
        d.rounded_rectangle([110 + inset, y, 760 - inset, y + lh], radius=16,
                            fill=pal.accent_soft if last else pal.soft, outline=pal.accent if last else pal.primary,
                            width=4)
        fw = 760 - 110 - 2 * inset - 80
        d.text((150 + inset, y + lh * 0.16), title, font=fonts.fit(d, title, fw, 32), fill=pal.ink)
        if desc:
            d.text((150 + inset, y + lh * 0.58), desc, font=fonts.fit(d, desc, fw, 24),
                   fill=pal.accent if last else pal.muted)
    x = 880
    if spec.get("label"):
        text_c(d, x, 52, spec["label"], fonts.fit(d, spec["label"], 260, 28), pal.accent)
    for y in range(110, 500, 26):
        d.line([(x, y), (x, y + 14)], fill=pal.accent, width=5)
    d.polygon([(x - 16, 495), (x + 16, 495), (x, 525)], fill=pal.accent)
    motif(d, "magnifier", x + 8, 568, 110, pal.accent, pal.accent)
    if spec.get("caption"):
        text_c(d, 435, 598, spec["caption"], fonts.fit(d, spec["caption"], 640, 26), pal.muted)


def fig_shift(spec, pal, fonts, d):
    for side, cx in (("before", 240), ("after", 840)):
        part = spec[side]
        after = side == "after"
        motif(d, part.get("motif", "chip"), cx, 255, 300, pal.primary, pal.accent, fill=pal.soft)
        if part.get("focus"):
            motif(d, "magnifier", cx + 20, 255, 170, pal.accent, pal.accent)
        text_c(d, cx, 440, part["title"], fonts.fit(d, part["title"], 400, 34), pal.accent if after else pal.ink)
        if part.get("desc"):
            text_c(d, cx, 492, part["desc"], fonts.fit(d, part["desc"], 400, 24), pal.muted)
    d.line([(430, 255), (610, 255)], fill=pal.accent, width=8)
    d.polygon([(610, 233), (648, 255), (610, 277)], fill=pal.accent)
    tags = spec.get("tags") or []
    if tags:
        pw = min(200, (FIG_W - 120) / len(tags) - 30)
        start = (FIG_W - (pw * len(tags) + 30 * (len(tags) - 1))) / 2
        for i, tag in enumerate(tags):
            x = start + i * (pw + 30)
            d.rounded_rectangle([x, 556, x + pw, 606], radius=25, outline=pal.primary, width=3)
            text_c(d, x + pw / 2, 566, tag, fonts.fit(d, tag, pw - 24, 24), pal.primary)


def fig_timeline(spec, pal, fonts, d):
    items = spec["items"]
    n = len(items)
    if spec.get("title"):
        text_c(d, FIG_W / 2, 110, spec["title"], fonts.fit(d, spec["title"], 960, 34), pal.primary)
    y = 330
    left, right = 150, FIG_W - 150
    step = (right - left) / (n - 1) if n > 1 else 0
    width = min(260, step - 26) if n > 1 else 600
    d.line([(left - 60, y), (right + 60, y)], fill=pal.line, width=6)
    body = fonts.get(24)
    for i, item in enumerate(items):
        when, what = item_pair(item)
        last = i == n - 1
        cx = left + step * i if n > 1 else FIG_W / 2
        r = 20 if last else 14
        d.ellipse([cx - r, y - r, cx + r, y + r], fill=pal.accent if last else pal.primary)
        text_c(d, cx, y - 82, when, fonts.fit(d, when, width, 34), pal.accent if last else pal.ink)
        for k, line in enumerate(wrap(d, what, body, width)[:5]):
            text_c(d, cx, y + 44 + k * 38, line, body, pal.ink if last else pal.muted)


def fig_bignum(spec, pal, fonts, d):
    f = fonts.fit(d, spec["value"], 920, 190, 60)
    text_c(d, FIG_W / 2, 150 - f.getbbox(spec["value"])[1], spec["value"], f, pal.accent, stroke=max(2, f.size // 40))
    d.rectangle([FIG_W / 2 - 60, 390, FIG_W / 2 + 60, 396], fill=pal.primary)
    lines = wrap(d, spec.get("label", ""), fonts.get(34), 880)[:2]
    for k, line in enumerate(lines):
        text_c(d, FIG_W / 2, 425 + k * 50, line, fonts.get(34), pal.ink)
    if spec.get("note"):
        text_c(d, FIG_W / 2, 560, spec["note"], fonts.fit(d, spec["note"], 900, 22), pal.muted)


FIGURES = {"compare": fig_compare, "stack": fig_stack, "shift": fig_shift,
           "timeline": fig_timeline, "bignum": fig_bignum}


def figure(spec: dict, pal: Palette, fonts: Fonts, out: Path) -> Path:
    kind = spec.get("type")
    if kind not in FIGURES:
        sys.exit(f"未知图形类型「{kind}」，可选：{'、'.join(FIGURES)}")
    img = Image.new("RGB", (FIG_W, FIG_H), pal.paper)
    FIGURES[kind](spec, pal, fonts, ImageDraw.Draw(img))
    grain(img, 3)
    path = out / f"{spec.get('name') or kind}.jpg"
    save_under_limit(img, path, MAX_KB)
    return path


# ---------- 入口 ----------

def load_colors(spec: dict, design_path: str | None) -> Palette:
    colors = dict(spec.get("colors") or {})
    if design_path:
        design = json.loads(Path(design_path).read_text(encoding="utf-8"))
        dc = design.get("colors") or {}
        colors.setdefault("primary", dc.get("primary"))
        colors.setdefault("accent", dc.get("accent"))
    if not colors.get("primary"):
        colors["primary"] = "#24477a"
    return Palette(colors["primary"], colors.get("accent"))


def main() -> int:
    ap = argparse.ArgumentParser(description="按选题生成大字报封面与正文信息图")
    ap.add_argument("spec", nargs="?", help="配图规格 JSON（结构见 --example）")
    ap.add_argument("-o", "--outdir", default="wx_images", help="输出目录，默认 wx_images")
    ap.add_argument("--design", help="render_layout / build_article 保存的设计方案，取主色与强调色")
    ap.add_argument("--font", help="中文字体文件；默认自动查找系统字体")
    ap.add_argument("--example", action="store_true", help="打印一份完整示例规格")
    ap.add_argument("--list", action="store_true", help="列出图形类型与图标")
    args = ap.parse_args()

    if args.example:
        print(json.dumps(EXAMPLE, ensure_ascii=False, indent=2))
        return 0
    if args.list:
        print("正文信息图类型：")
        for k, v in FIG_TYPES.items():
            print(f"  {k:<9} {v}")
        print("图标（封面两侧装饰、信息图主体）：")
        for k in MOTIFS:
            print(f"  {k:<9} {MOTIF_DESC[k]}")
        return 0
    if not args.spec:
        ap.error("需要配图规格 JSON（或用 --example 先看示例）")

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    pal = load_colors(spec, args.design)
    fonts = Fonts(*find_font(args.font))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    made = []
    if spec.get("cover"):
        if not spec["cover"].get("headline"):
            sys.exit("cover.headline 不能为空：封面要用大字点出主题")
        made += cover(spec["cover"], pal, fonts, out)
    for fig in spec.get("figures") or []:
        made.append(figure(fig, pal, fonts, out))
    for path in made:
        with Image.open(path) as im:
            print(f"{path}  {im.size[0]}x{im.size[1]}  {round(path.stat().st_size / 1024, 1)} KB")
    print(f"共 {len(made)} 张，可用 prepare_image.py {out} --check-only 复核；封面先看 cover_11.jpg 缩略后是否一眼能认出主题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
