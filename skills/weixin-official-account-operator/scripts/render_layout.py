#!/usr/bin/env python3
"""公众号排版设计渲染器：按选题为每篇文章组合一份设计方案，渲染成微信安全的内联样式 HTML。

没有固定模版。设计方案 = 调性（字号节奏与组件倾向）+ 配色（按选题联想，或品牌色）+ 每个组件选一种样式，
由 Agent 按选题决定；--auto 给出带理由的起点方案，Agent 在此基础上改。

用法：
  1) 自动设计方案（JSON，含每项理由）：render_layout.py 正文.md --auto [--hint "国风 高级感"]
  2) 按方案渲染：render_layout.py 正文.md [--design 方案.json] [--mood tech] [--palette autumn]
       [--primary #RRGGBB] [--accent #RRGGBB] [--set h2=part,figure=round] [--density large]
       -o out.html [--save-design 方案.json]
  3) 样式库预览（每个组件的全部样式 + 全部配色）：render_layout.py --gallery 样式库.html [--palette x]
  4) 列出调性 / 配色 / 组件样式：render_layout.py --list

样式库唯一数据源是 ../assets/styles.json。仅依赖标准库。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "assets" / "styles.json"

FENCED = re.compile(r"^:::(card|cta|stat|note|html|masthead|code|steps|tip|warn|follow|points|compare)\s*(.*)$")
RAW_BLOCKS = ("html", "code")  # 保留原始缩进与空格的块
IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
HR = re.compile(r"^(-{3,}|\*{3,})$")
NUMBERED_H2 = {"chip", "part", "no", "numeral", "hero"}  # 自带序号的标题样式
CN_NUM = "零壹贰叁肆伍陆柒捌玖拾"
MONO = "Menlo,Consolas,'Courier New',monospace"


# ---------------------------------------------------------------- 样式库

def load_library(path: Path = LIBRARY_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def by_id(items: list[dict], item_id: str, kind: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return item
    raise SystemExit(f"未找到{kind} {item_id}；用 --list 查看可用项")


def variants(lib: dict, slot: str) -> list[str]:
    return [k for k in lib["components"][slot] if not k.startswith("_")]


# ---------------------------------------------------------------- 颜色工具

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise SystemExit(f"颜色格式无效：{value}（应为 #RRGGBB）")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def normalize(color: str) -> str:
    return rgb_to_hex(hex_to_rgb(color))


def mix(color: str, other: str, ratio: float) -> str:
    """ratio 为 other 的占比，0=返回 color，1=返回 other。"""
    a, b = hex_to_rgb(color), hex_to_rgb(other)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))


def _lin(channel: float) -> float:
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    r, g, b = (_lin(c) for c in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1: str, c2: str) -> float:
    l1, l2 = sorted((luminance(c1), luminance(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def readable_text(bg: str) -> str:
    """在给定背景色上选择对比度更高的黑或白。"""
    return "#ffffff" if contrast(bg, "#ffffff") >= contrast(bg, "#111111") else "#111111"


def ink_of(color: str, target: float = 4.5) -> str:
    """当文字色用时逐步压暗，直到在白底上达到目标对比度（浅色品牌色不直接当字色）。"""
    ink = color
    for _ in range(20):
        if contrast(ink, "#ffffff") >= target:
            break
        ink = mix(ink, "#000000", 0.08)
    return ink


# ---------------------------------------------------------------- 设计方案

DENSITY = {
    "large": {"font_delta": 1, "line_height": 1.95, "gap_delta": 4, "label": "大字宽松"},
    "standard": None,
    "compact": {"font_delta": -1, "line_height": 1.7, "gap_delta": -4, "label": "紧凑"},
}

PROMO_RE = re.compile(r"限时|截止|报名|席位|倒计时|优惠|元/年|立减|抢购")
STEP_RE = re.compile(r"第[一二三四五六七八九十\d]+\s*[步章节]|步骤\s*\d|^:::steps", re.M)


def _hits(words: list[str], low: str) -> list[str]:
    return [w for w in words if w.lower() in low]


def score_moods(text: str, lib: dict, hint: str = "") -> list[dict]:
    """按用户风格词、选题信号词与结构特征给调性打分，降序返回。"""
    low = text.lower()
    paras = [p for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 30]
    long_paras = bool(paras) and sum(len(p) for p in paras) / len(paras) > 120
    festival = any(_hits(p["topics"], low) for p in lib["palettes"] if p.get("festival") and
                   p["id"] not in ("spring", "summer", "autumn", "winter"))
    results = []
    for mood in lib["moods"]:
        score, reasons = 0, []
        for word in mood["words"]:
            if word in hint:
                score += 12
                reasons.append(f"你要求「{word}」")
            elif word in text:
                score += 6
                reasons.append(f"文中提到「{word}」")
        hits = _hits(mood["signals"], low)
        score += min(len(hits) * 3, 24)
        if hits:
            reasons.append("选题信号：" + "、".join(hits[:4]))
        mid = mood["id"]
        if mid == "tutorial" and STEP_RE.search(text):
            score += 4
            reasons.append("有分步骤结构")
        if mid == "tech" and re.search(r"^:::code|^\$ ", text, re.M):
            score += 4
            reasons.append("有命令/代码")
        if mid in ("business", "tutorial") and len(re.findall(r"\d+(\.\d+)?%", text)) >= 3:
            score += 2
            reasons.append("多组百分比数据")
        if mid == "promo" and PROMO_RE.search(text):
            score += 6
            reasons.append("有活动/时限表述")
        if mid in ("warm", "editorial") and len(re.findall(r"[“”\"]", text)) >= 4:
            score += 3 if mid == "warm" else 2
            reasons.append("引语/对话多")
        if mid == "editorial" and long_paras:
            score += 3
            reasons.append("长段落为主，偏深度阅读")
        if mid == "festive" and festival:
            score += 6
            reasons.append("节日选题")
        results.append({"id": mid, "name": mood["name"], "score": score, "reasons": reasons[:4]})
    order = {m["id"]: i for i, m in enumerate(lib["moods"])}
    return sorted(results, key=lambda r: (-r["score"], order[r["id"]]))


def score_palettes(text: str, lib: dict, mood_id: str, hint: str = "") -> list[dict]:
    """按选题联想给配色打分：话题词命中、节日/节气优先、调性默认色兜底。
    用户点名了风格词时，调性默认色权重更高（「国风」不该配商务蓝），但节日联想仍然优先。"""
    low = (text + " " + hint).lower()
    mood = by_id(lib["moods"], mood_id, "调性")
    default = mood["palette"]
    bonus = 7 if any(w in hint for w in mood["words"]) else 2
    results = []
    for pal in lib["palettes"]:
        hits = _hits(pal["topics"], low)
        score = len(hits) * 3 + (4 if hits and pal.get("festival") else 0)
        reasons = ["选题联想：" + "、".join(hits[:4])] if hits else []
        if pal["id"] == default:
            score += bonus
            reasons.append("调性默认色")
        results.append({"id": pal["id"], "name": pal["name"], "score": score, "reasons": reasons})
    order = {p["id"]: i for i, p in enumerate(lib["palettes"])}
    return sorted(results, key=lambda r: (-r["score"], order[r["id"]]))


def h2_texts(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", text, re.M)]


def pick_components(text: str, lib: dict, mood: dict) -> tuple[dict, list[str]]:
    """每个组件取调性的首选样式，再按文章结构修正，返回 (组件表, 理由)。"""
    comps = {slot: (mood["prefer"].get(slot) or variants(lib, slot))[0] for slot in lib["components"]}
    reasons = []
    heads = h2_texts(text)
    prefs = mood["prefer"].get("h2", [])
    plain = [v for v in prefs if v not in NUMBERED_H2] or ["bar"]
    if heads and all(re.match(r"^(\d+|[一二三四五六七八九十]+)[.、．\s]|^第", h) for h in heads):
        if comps["h2"] in NUMBERED_H2:
            comps["h2"] = plain[0]
            reasons.append(f"小标题自带序号，标题用不带编号的「{comps['h2']}」避免重复编号")
    elif len(heads) <= 1 and comps["h2"] in NUMBERED_H2:
        comps["h2"] = plain[0]
        reasons.append(f"只有 {len(heads)} 个小标题，编号没有意义，改用「{comps['h2']}」")
    elif len(heads) >= 4 and comps["h2"] not in NUMBERED_H2:
        numbered = [v for v in prefs if v in NUMBERED_H2]
        if numbered:
            comps["h2"] = numbered[0]
            reasons.append(f"{len(heads)} 个小标题，用带序号的「{comps['h2']}」方便定位")
    steps = re.search(r"^:::steps.*\n((?:(?!:::).*\n)*)", text, re.M)
    if steps and comps["steps"] == "cards" and len([x for x in steps.group(1).split("\n") if x.strip()]) > 5:
        comps["steps"] = "timeline"
        reasons.append("步骤超过 5 步，用竖线串联更紧凑")
    return comps, reasons


def auto_design(text: str, lib: dict, hint: str = "", mood_id: str | None = None,
                palette_id: str | None = None) -> dict:
    """按选题自动组合设计方案（可被 --design / 参数逐项覆盖）。"""
    reasons = []
    moods = score_moods(text, lib, hint)
    if mood_id:
        mood = by_id(lib["moods"], mood_id, "调性")
        reasons.append(f"调性：{mood['name']}（按指定）")
    else:
        top = moods[0]
        mood = by_id(lib["moods"], top["id"] if top["score"] > 0 else "business", "调性")
        why = "；".join(top["reasons"]) if top["score"] > 0 else "没有明显的风格信号，用最通用的稳重商务"
        reasons.append(f"调性：{mood['name']}（{why}）")

    if palette_id:
        pal = by_id(lib["palettes"], palette_id, "配色")
        reasons.append(f"配色：{pal['name']}（按指定）")
    else:
        top = score_palettes(text, lib, mood["id"], hint)[0]
        pal = by_id(lib["palettes"], top["id"], "配色")
        reasons.append(f"配色：{pal['name']} {pal['primary']}（{'；'.join(top['reasons'])}）")

    comps, why = pick_components(text, lib, mood)
    reasons += why
    return {
        "name": f"{pal['name']} · {mood['name']}",
        "mood": mood["id"],
        "palette": pal["id"],
        "colors": {"primary": pal["primary"], "accent": pal.get("accent") or pal["primary"]},
        "typography": dict(mood["typography"]),
        "density": "standard",
        "components": comps,
        "numbered": False,
        "ornament": mood.get("ornament", "◆"),
        "reasons": reasons,
    }


def parse_sets(value: str | None) -> dict:
    out = {}
    for pair in (value or "").split(","):
        if pair.strip():
            slot, _, var = pair.partition("=")
            out[slot.strip()] = var.strip()
    return out


def resolve_design(text: str, lib: dict, spec: dict | None = None, hint: str = "") -> dict:
    """自动方案打底，再叠加 Agent 写的方案（部分字段即可）。"""
    spec = spec or {}
    design = auto_design(text, lib, hint, spec.get("mood"), spec.get("palette"))
    if spec.get("palette") and not spec.get("colors"):
        pal = by_id(lib["palettes"], spec["palette"], "配色")
        design["colors"] = {"primary": pal["primary"], "accent": pal.get("accent") or pal["primary"]}
    colors = spec.get("colors") or {}
    if colors.get("primary"):
        design["colors"]["primary"] = normalize(colors["primary"])
        design["colors"]["accent"] = normalize(colors.get("accent") or colors["primary"])
        design["palette"] = None
        design["reasons"].append(f"配色：主色 {design['colors']['primary']}（按指定）")
    elif colors.get("accent"):
        design["colors"]["accent"] = normalize(colors["accent"])
    design["typography"].update(spec.get("typography") or {})
    for slot, var in (spec.get("components") or {}).items():
        if slot not in lib["components"]:
            raise SystemExit(f"未知组件 {slot}；可用：{'、'.join(lib['components'])}")
        if var not in variants(lib, slot):
            raise SystemExit(f"组件 {slot} 没有样式 {var}；可用：{'、'.join(variants(lib, slot))}")
        if design["components"][slot] != var:
            design["components"][slot] = var
            design["reasons"].append(f"{lib['components'][slot]['_slot']}：{var}（按指定）")
    for key in ("name", "numbered", "ornament", "density"):
        if key in spec:
            design[key] = spec[key]
    if "name" not in spec and colors.get("primary"):
        design["name"] = f"定制 {design['colors']['primary']} · {by_id(lib['moods'], design['mood'], '调性')['name']}"
    if design["density"] not in DENSITY:
        raise SystemExit(f"density 只能是 {'/'.join(DENSITY)}")
    return design


def design_tokens(design: dict, lib: dict) -> dict:
    """把设计方案展开成渲染用 token：颜色全部从主色/强调色派生，保证整篇只有一个主强调色。"""
    mood = by_id(lib["moods"], design["mood"], "调性")
    primary = normalize(design["colors"]["primary"])
    accent = normalize(design["colors"].get("accent") or primary)
    typo = dict(design["typography"])
    spec = DENSITY.get(design.get("density") or "standard")
    if spec:
        typo["font_size"] = max(14, min(18, typo["font_size"] + spec["font_delta"]))
        typo["line_height"] = spec["line_height"]
        typo["para_gap"] = max(12, typo["para_gap"] + spec["gap_delta"])
    text = mood.get("text", "#333333")
    return {
        "primary": primary,
        "accent": accent,
        "primary_ink": ink_of(primary),
        "accent_ink": ink_of(accent),
        "on_primary": "#ffffff" if contrast(primary, "#ffffff") >= 3 else "#111111",
        "primary_soft": mix(primary, "#ffffff", 0.9),
        "primary_line": mix(primary, "#ffffff", 0.6),
        "dark": mix(primary, "#000000", 0.78),
        "deep": mix(primary, "#000000", 0.55),
        "text": text,
        "heading": mix(text, "#000000", 0.25),
        "text_muted": mix(text, "#ffffff", 0.3),
        "bg_soft": mix(primary, "#f7f7f7", 0.94),
        "accent_soft": mix(accent, "#ffffff", 0.9),
        "mark": mix(accent, "#ffffff", 0.8),
        "pop": accent if accent != primary else mix(primary, "#ffffff", 0.45),
        "divider": mix(primary, "#e6e6e6", 0.88),
        "font_size": typo["font_size"],
        "line_height": typo["line_height"],
        "para_gap": typo["para_gap"],
        "letter_spacing": typo.get("letter_spacing", "0.3px"),
        "numbered": bool(design.get("numbered")),
        "ornament": design.get("ornament") or "◆",
        "c": dict(design["components"]),
    }


# ---------------------------------------------------------------- 内容解析

def inline(text: str, t: dict) -> str:
    """转义后应用行内样式：加粗、斜体、代码、链接。"""
    out = html.escape(text, quote=False)
    out = re.sub(r"==(.+?)==",
                 lambda m: f'<strong style="padding:0 2px;background-color:{t["mark"]};color:{t["heading"]};">'
                           f'{m.group(1)}</strong>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`",
                 lambda m: f'<code style="padding:2px 6px;background-color:{t["bg_soft"]};'
                           f'color:{t["primary_ink"]};border-radius:3px;font-size:0.92em;">{m.group(1)}</code>',
                 out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"<strong>\1</strong>", out)
    return out


def parse_markdown(text: str) -> list[dict]:
    """解析受支持的 Markdown 子集为块列表。"""
    blocks: list[dict] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i, paragraph = 0, []

    def flush() -> None:
        if paragraph:
            blocks.append({"type": "p", "text": " ".join(paragraph).strip()})
            paragraph.clear()

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            flush()
            i += 1
            continue

        fenced = FENCED.match(line)
        if fenced:
            flush()
            kind, arg = fenced.group(1), fenced.group(2).strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i].rstrip() if kind in RAW_BLOCKS else lines[i].strip())
                i += 1
            i += 1
            blocks.append({"type": kind, "arg": arg, "text": "\n".join(body).strip()})
            continue

        if HR.match(line):
            flush()
            blocks.append({"type": "hr"})
            i += 1
            continue

        heading = HEADING.match(line)
        if heading:
            flush()
            blocks.append({"type": "h", "level": len(heading.group(1)), "text": heading.group(2).strip()})
            i += 1
            continue

        image = IMAGE.match(line)
        if image:
            flush()
            blocks.append({"type": "img", "alt": image.group(1), "src": image.group(2)})
            i += 1
            continue

        if line.startswith("> "):
            flush()
            quote = [line[2:].strip()]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append({"type": "quote", "text": " ".join(quote)})
            continue

        for kind, pattern in (("ul", r"^[-*]\s+"), ("ol", r"^\d+[.)]\s+")):
            if re.match(pattern, line):
                flush()
                items = []
                while i < len(lines) and re.match(pattern, lines[i].strip()):
                    items.append(re.sub(pattern, "", lines[i].strip()))
                    i += 1
                blocks.append({"type": kind, "items": items})
                break
        else:
            paragraph.append(line)
            i += 1

    flush()
    return blocks


# ---------------------------------------------------------------- 组件渲染
# 每个组件按 t["c"][组件] 选样式；颜色只用 token，换配色时整篇一起变。

def split_pair(text: str) -> tuple[str, str]:
    parts = re.split(r"\s*[|｜]\s*", text, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""


def short_bar(t: dict, align: str = "left", margin: str = "10px 0 0") -> str:
    return (f'<p style="margin:{margin};font-size:0;line-height:0;text-align:{align};">'
            f'<span style="display:inline-block;width:28px;height:3px;background-color:{t["primary"]};"></span></p>')


def cn_num(n: int) -> str:
    if n <= 10:
        return CN_NUM[n]
    return ("" if n < 20 else CN_NUM[n // 10]) + "拾" + (CN_NUM[n % 10] if n % 10 else "")


def render_h2(text: str, idx: int, t: dict) -> str:
    style, fs = t["c"]["h2"], t["font_size"] + 3
    body = inline(text, t)
    prefix = (f'<span style="color:{t["primary_ink"]};margin-right:8px;">{idx:02d}</span>'
              if t["numbered"] and style not in NUMBERED_H2 else "")
    base = f"font-size:{fs}px;line-height:1.4;font-weight:bold;"
    if style == "underline":
        return (f'<h2 style="margin:32px 0 16px;{base}padding-bottom:8px;color:{t["heading"]};'
                f'border-bottom:2px solid {t["primary"]};">{prefix}{body}</h2>')
    if style == "chip":
        return (f'<h2 style="margin:32px 0 16px;{base}padding-bottom:10px;color:{t["heading"]};'
                f'border-bottom:1px solid {t["divider"]};"><span style="display:inline-block;margin-right:10px;'
                f'padding:1px 8px;font-size:14px;line-height:1.6;vertical-align:2px;background-color:{t["primary"]};'
                f'color:{t["on_primary"]};border-radius:4px;">{idx:02d}</span>{body}</h2>')
    if style == "part":
        return (f'<section style="margin:36px 0 16px;"><p style="margin:0 0 6px;font-size:12px;line-height:1.4;'
                f'letter-spacing:3px;font-weight:bold;color:{t["primary_ink"]};">PART {idx:02d}</p>'
                f'<h2 style="margin:0;{base}color:{t["heading"]};">{body}</h2>{short_bar(t)}</section>')
    if style == "no":
        return (f'<section style="margin:36px 0 16px;"><p style="margin:0;font-size:30px;line-height:1.1;'
                f'font-style:italic;font-weight:bold;font-family:Georgia,serif;color:{t["primary_line"]};">'
                f'NO.{idx:02d}</p><h2 style="margin:4px 0 0;{base}color:{t["heading"]};padding-bottom:8px;'
                f'border-bottom:1px solid {t["divider"]};">{body}</h2></section>')
    if style == "numeral":
        return (f'<section style="margin:40px 0 18px;text-align:center;"><p style="margin:0;font-size:22px;'
                f'line-height:1.3;letter-spacing:2px;color:{t["accent_ink"]};">{cn_num(idx)}</p>'
                f'<h2 style="margin:6px 0 0;{base}letter-spacing:3px;color:{t["heading"]};">{body}</h2>'
                f'{short_bar(t, "center")}</section>')
    if style == "hero":
        return (f'<section style="margin:40px 0 18px;"><h2 style="margin:0;{base}color:{t["heading"]};">'
                f'<span style="margin-right:12px;font-size:{fs + 19}px;line-height:1;font-family:Georgia,serif;'
                f'font-style:italic;color:{t["primary_ink"]};vertical-align:-4px;">{idx:02d}</span>{body}</h2>'
                f'<p style="margin:10px 0 0;font-size:0;line-height:0;">'
                f'<span style="display:inline-block;width:56px;height:3px;background-color:{t["primary"]};"></span>'
                f'<span style="display:inline-block;width:14px;height:3px;margin-left:4px;'
                f'background-color:{t["pop"]};"></span></p></section>')
    if style == "center":
        return (f'<h2 style="margin:36px 0 18px;{base}color:{t["heading"]};text-align:center;padding:14px 0;'
                f'border-top:1px solid {t["divider"]};border-bottom:1px solid {t["divider"]};">{prefix}{body}</h2>')
    if style == "block":
        return (f'<h2 style="margin:32px 0 16px;{base}padding:10px 14px;background-color:{t["primary"]};'
                f'color:{t["on_primary"]};border-radius:4px;">{prefix}{body}</h2>')
    if style == "pill":
        return (f'<h2 style="margin:32px 0 16px;{base}"><span style="display:inline-block;padding:6px 18px;'
                f'background-color:{t["primary"]};color:{t["on_primary"]};border-radius:999px;">'
                f'{prefix}{body}</span></h2>')
    return (f'<h2 style="margin:32px 0 16px;{base}color:{t["heading"]};padding-left:12px;'
            f'border-left:4px solid {t["primary"]};">{prefix}{body}</h2>')  # bar


def render_h3(text: str, t: dict) -> str:
    style = t["c"]["h3"]
    base = f'margin:26px 0 12px;font-size:{t["font_size"] + 1}px;line-height:1.5;font-weight:bold;'
    if style == "dot":
        return (f'<h3 style="{base}color:{t["heading"]};"><span style="display:inline-block;width:8px;height:8px;'
                f'margin-right:8px;vertical-align:2px;background-color:{t["primary"]};"></span>{inline(text, t)}</h3>')
    color = t["primary_ink"] if style == "color" else t["heading"]
    return f'<h3 style="{base}color:{color};">{inline(text, t)}</h3>'


def render_lead(text: str, t: dict) -> str:
    style, fs, lh, gap = t["c"]["lead"], t["font_size"], t["line_height"], t["para_gap"]
    if style == "guide":
        return (f'<section style="margin:0 0 {gap + 8}px;padding:16px 16px 14px;background-color:{t["bg_soft"]};'
                f'border-left:4px solid {t["primary"]};border-radius:0 8px 8px 0;">'
                f'<p style="margin:0 0 6px;font-size:13px;line-height:1.4;font-weight:bold;letter-spacing:2px;'
                f'color:{t["primary_ink"]};">导读</p><p style="margin:0;font-size:{fs}px;line-height:{lh};'
                f'color:{t["heading"]};">{inline(text, t)}</p></section>')
    if style == "boxed":
        return (f'<section style="margin:0 0 {gap + 6}px;padding:14px 16px;background-color:{t["bg_soft"]};'
                f'border-radius:6px;"><p style="margin:0;font-size:{fs}px;line-height:{lh};color:{t["text_muted"]};">'
                f'{inline(text, t)}</p></section>')
    color, weight = (t["heading"], "bold") if style == "bold" else (t["text_muted"], "normal")
    return (f'<p style="margin:0 0 {gap + 4}px;color:{color};font-weight:{weight};'
            f'font-size:{fs}px;line-height:{lh};">{inline(text, t)}</p>')


def render_quote(text: str, t: dict) -> str:
    style, fs, lh = t["c"]["quote"], t["font_size"], t["line_height"]
    if style == "center":
        return (f'<section style="margin:30px 8px;text-align:center;"><p style="margin:0;font-size:36px;'
                f'line-height:1;font-family:Georgia,serif;color:{t["primary_line"]};">“</p>'
                f'<p style="margin:4px 0 0;font-size:{fs}px;line-height:{lh};font-weight:bold;color:{t["heading"]};">'
                f'{inline(text, t)}</p>{short_bar(t, "center", "14px 0 0")}</section>')
    if style == "card":
        return (f'<section style="margin:30px 0;padding:22px 20px 20px;background-color:{t["deep"]};'
                f'border-radius:10px;"><p style="margin:0;font-size:44px;line-height:0.8;font-family:Georgia,serif;'
                f'color:{t["pop"]};">“</p><p style="margin:10px 0 0;font-size:{fs + 1}px;line-height:{lh};'
                f'font-weight:bold;letter-spacing:1px;color:#ffffff;">{inline(text, t)}</p>'
                f'<p style="margin:14px 0 0;font-size:0;line-height:0;text-align:right;"><span style="display:inline-block;'
                f'width:28px;height:3px;background-color:{t["pop"]};"></span></p></section>')
    if style == "soft":
        return (f'<blockquote style="margin:24px 0;padding:16px 18px;background-color:{t["primary_soft"]};'
                f'border-radius:8px;color:{t["text"]};font-size:{fs}px;line-height:{lh};">'
                f'{inline(text, t)}</blockquote>')
    return (f'<blockquote style="margin:24px 0;padding:14px 16px;background-color:{t["bg_soft"]};'
            f'border-left:3px solid {t["primary_line"]};color:{t["text_muted"]};font-size:{fs}px;'
            f'line-height:{lh};">{inline(text, t)}</blockquote>')


def render_card(text: str, t: dict, label: str = "") -> str:
    style, fs, lh = t["c"]["card"], t["font_size"], t["line_height"]
    paras = [p for p in text.split("\n") if p.strip()] or [text]
    inner = "".join(f'<p style="margin:0 0 {0 if k == len(paras) - 1 else 10}px;line-height:{lh};'
                    f'font-size:{fs}px;">{inline(p, t)}</p>' for k, p in enumerate(paras))
    if style == "border":
        box = f'border:1px solid {t["primary_line"]};border-radius:4px;color:{t["text"]};'
    elif style == "soft":
        box = f'background-color:{t["primary_soft"]};border-radius:10px;color:{t["text"]};'
    else:
        box = (f'background-color:{t["bg_soft"]};border-left:3px solid {t["primary"]};'
               f'border-radius:6px;color:{t["text_muted"]};')
    tag = (f'<p style="margin:0 0 10px;"><span style="display:inline-block;padding:2px 10px;font-size:12px;'
           f'line-height:1.7;font-weight:bold;letter-spacing:1px;background-color:{t["primary"]};'
           f'color:{t["on_primary"]};border-radius:3px;">{inline(label, t)}</span></p>') if label else ""
    return f'<section style="margin:24px 0;padding:16px 18px;{box}">{tag}{inner}</section>'


def render_points(block: dict, t: dict) -> str:
    """要点卡 :::points 标签；每行一条要点（2–4 条最好），适合放在导语之后。"""
    fs, lh = t["font_size"], t["line_height"]
    rows = [ln for ln in block["text"].split("\n") if ln.strip()]
    label = inline(block["arg"] or "本文要点", t)
    if t["c"].get("points") == "cards":
        items = "".join(
            f'<section style="margin:0 0 10px;padding:12px 14px;background-color:#ffffff;border-radius:8px;'
            f'border-top:3px solid {t["primary"] if k else t["pop"]};"><p style="margin:0;font-size:{fs - 1}px;'
            f'line-height:{lh};color:{t["text"]};"><span style="margin-right:8px;font-weight:bold;font-family:Georgia,'
            f'serif;color:{t["primary_ink"]};">{k + 1:02d}</span>{inline(r, t)}</p></section>'
            for k, r in enumerate(rows))
        return (f'<section style="margin:24px 0;padding:16px 14px 6px;background-color:{t["primary_soft"]};'
                f'border-radius:10px;"><p style="margin:0 0 12px;font-size:14px;font-weight:bold;letter-spacing:2px;'
                f'color:{t["primary_ink"]};">{label}</p>{items}</section>')
    items = "".join(
        f'<p style="margin:0 0 {0 if k == len(rows) - 1 else 12}px;font-size:{fs - 1}px;line-height:{lh};'
        f'color:{t["text"]};"><span style="display:inline-block;width:22px;height:22px;margin-right:10px;'
        f'line-height:22px;text-align:center;font-size:12px;font-weight:bold;border-radius:50%;'
        f'background-color:{t["primary"]};color:{t["on_primary"]};vertical-align:1px;">{k + 1}</span>{inline(r, t)}</p>'
        for k, r in enumerate(rows))
    return (f'<section style="margin:24px 0;padding:18px 16px;border:1px solid {t["primary_line"]};border-radius:10px;">'
            f'<p style="margin:0 0 14px;font-size:14px;font-weight:bold;letter-spacing:2px;color:{t["primary_ink"]};">'
            f'<span style="display:inline-block;width:4px;height:14px;margin-right:8px;vertical-align:-1px;'
            f'background-color:{t["pop"]};"></span>{label}</p>{items}</section>')


def render_compare(block: dict, t: dict) -> str:
    """对照卡 :::compare 左标题 | 右标题；每行「左 | 右」。左边是旧/误解，右边是新/真相（高亮）。"""
    fs, lh = t["font_size"], t["line_height"]
    left, right = split_pair(block["arg"] or "以前 | 现在")
    rows = [split_pair(ln) for ln in block["text"].split("\n") if ln.strip()]

    def col(title: str, cells: list[str], hot: bool, width: str) -> str:
        head_bg = t["primary"] if hot else t["divider"]
        head_fg = t["on_primary"] if hot else t["heading"]
        body = "".join(f'<p style="margin:0 0 10px;font-size:{fs - 1}px;line-height:{lh};'
                       f'color:{t["heading"] if hot else t["text_muted"]};">{inline(c, t)}</p>' for c in cells if c)
        return (f'<section style="display:inline-block;width:{width};vertical-align:top;box-sizing:border-box;'
                f'white-space:normal;font-size:{fs}px;'
                f'background-color:{t["primary_soft"] if hot else t["bg_soft"]};border-radius:8px;overflow:hidden;">'
                f'<p style="margin:0;padding:8px 12px;font-size:14px;font-weight:bold;text-align:center;'
                f'background-color:{head_bg};color:{head_fg};">{inline(title, t)}</p>'
                f'<section style="padding:12px 12px 2px;">{body}</section></section>')

    lefts, rights = [a for a, _ in rows], [b for _, b in rows]
    if t["c"].get("compare") == "stacked":
        return (f'<section style="margin:24px 0;">{col(left, lefts, False, "100%")}'
                f'<p style="margin:8px 0;text-align:center;font-size:16px;color:{t["pop"]};">▼</p>'
                f'{col(right, rights, True, "100%")}</section>')
    return (f'<section style="margin:24px 0;white-space:nowrap;font-size:0;">{col(left, lefts, False, "48%")}'
            f'<section style="display:inline-block;width:4%;"></section>{col(right, rights, True, "48%")}</section>')


def render_cta(text: str, t: dict) -> str:
    style, fs, lh = t["c"]["cta"], t["font_size"], t["line_height"]
    if style == "outline":
        box = (f'border:1px solid {t["primary"]};border-radius:6px;color:{t["primary_ink"]};'
               f'background-color:#ffffff;text-align:left;')
    elif style == "center":
        box = (f'background-color:{t["primary"]};color:{t["on_primary"]};border-radius:24px;'
               f'text-align:center;')
    else:
        box = f'background-color:{t["primary"]};color:{t["on_primary"]};border-radius:6px;text-align:left;'
    return (f'<section style="margin:28px 0;padding:16px 18px;{box}font-size:{fs}px;line-height:{lh};'
            f'font-weight:bold;">{inline(text, t)}</section>')


def render_stat(arg: str, text: str, t: dict) -> str:
    value, _, note = arg.partition("|")
    value, note = value.strip() or text.strip(), note.strip()
    boxed = t["c"]["stat"] == "boxed"
    box = f'padding:20px 16px;background-color:{t["primary_soft"]};border-radius:8px;' if boxed else "padding:18px 0;"
    return (f'<section style="margin:28px 0;{box}text-align:center;">'
            f'<p style="margin:0;font-size:{t["font_size"] + 16}px;font-weight:bold;color:{t["accent_ink"]};'
            f'line-height:1.2;">{html.escape(value, quote=False)}</p>'
            + (f'<p style="margin:8px 0 0;font-size:13px;color:{t["text_muted"]};line-height:1.6;">'
               f'{html.escape(note, quote=False)}</p>' if note else "")
            + "</section>")


def render_divider(t: dict) -> str:
    style = t["c"]["divider"]
    if style == "dots":
        return (f'<p style="margin:30px 0;text-align:center;color:{t["primary_line"]};font-size:14px;'
                f'letter-spacing:8px;">• • •</p>')
    if style == "short":
        return short_bar(t, "center", "32px 0")
    if style == "ornament":
        orn = t["ornament"]
        return (f'<p style="margin:30px 0;text-align:center;color:{t["accent_ink"]};font-size:12px;'
                f'letter-spacing:6px;">{orn} {orn} {orn}</p>')
    return (f'<section style="margin:30px 0;height:1px;line-height:1px;font-size:0;'
            f'background-color:{t["divider"]};">&nbsp;</section>')


def render_figure(block: dict, t: dict, caption: bool) -> str:
    style = t["c"]["figure"]
    src, alt = html.escape(block["src"], quote=True), html.escape(block["alt"], quote=True)
    if style == "shadow":
        deco = "border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.12);"
    elif style == "frame":
        deco = f"padding:6px;box-sizing:border-box;border:1px solid {t['primary_line']};border-radius:4px;"
    elif style == "round":
        deco = "border-radius:14px;"
    elif style == "card":
        out = (f'<section style="margin:26px 0;padding:8px 8px 10px;background-color:{t["bg_soft"]};border-radius:10px;">'
               f'<img src="{src}" alt="{alt}" style="display:block;width:100%;height:auto;margin:0 auto;'
               f'border-radius:6px;" />')
        if caption and block["alt"]:
            out += (f'<p style="margin:10px 4px 0;font-size:13px;line-height:1.6;color:{t["text_muted"]};">'
                    f'<span style="display:inline-block;width:3px;height:12px;margin-right:8px;vertical-align:-1px;'
                    f'background-color:{t["pop"]};"></span>{html.escape(block["alt"], quote=False)}</p>')
        return out + "</section>"
    else:
        deco = ""
    out = (f'<section style="margin:24px 0;text-align:center;">'
           f'<img src="{src}" alt="{alt}" style="display:block;width:100%;height:auto;margin:0 auto;{deco}" />')
    if caption and block["alt"]:
        out += (f'<p style="margin:10px 0 0;font-size:13px;line-height:1.6;color:{t["text_muted"]};">'
                f'{html.escape(block["alt"], quote=False)}</p>')
    return out + "</section>"


def render_masthead(block: dict, t: dict) -> str:
    """刊头：arg 为栏目标签；正文第一行为大标题，其余行为副题。"""
    style, fs = t["c"]["masthead"], t["font_size"]
    lines = [ln for ln in block["text"].split("\n") if ln.strip()]
    title = inline(lines[0], t) if lines else ""
    subs = lines[1:]
    kicker = inline(block["arg"], t) if block["arg"] else ""

    if style == "poster":
        chip = (f'<p style="margin:0 0 16px;"><span style="display:inline-block;padding:3px 12px;font-size:12px;'
                f'font-weight:bold;letter-spacing:2px;background-color:{t["pop"]};color:{readable_text(t["pop"])};'
                f'border-radius:2px;">'
                f'{kicker}</span></p>') if kicker else ""
        sub = "".join(f'<p style="margin:10px 0 0;font-size:{fs - 1}px;line-height:1.75;color:#c9d3e3;">'
                      f'{inline(s, t)}</p>' for s in subs)
        return (f'<section style="margin:0 0 30px;background-color:{t["deep"]};border-radius:10px;overflow:hidden;">'
                f'<section style="height:5px;line-height:5px;font-size:0;background-color:{t["pop"]};">&nbsp;</section>'
                f'<section style="padding:26px 22px 24px;">{chip}'
                f'<p style="margin:0;font-size:{fs + 10}px;line-height:1.35;font-weight:bold;letter-spacing:1px;'
                f'color:#ffffff;">{title}</p>{sub}'
                f'<p style="margin:20px 0 0;font-size:0;line-height:0;">'
                f'<span style="display:inline-block;width:48px;height:3px;background-color:{t["primary_line"]};"></span>'
                f'<span style="display:inline-block;width:12px;height:3px;margin-left:5px;'
                f'background-color:{t["pop"]};"></span></p></section></section>')

    if style == "dark":
        chip = (f'<p style="margin:0 0 14px;"><span style="display:inline-block;padding:2px 10px;'
                f'border:1px solid {t["primary"]};color:#ffffff;font-size:12px;letter-spacing:1px;'
                f'border-radius:4px;">{kicker}</span></p>') if kicker else ""
        sub = "".join(f'<p style="margin:8px 0 0;font-size:{fs - 2}px;line-height:1.7;color:#c9d3e3;">'
                      f'{inline(s, t)}</p>' for s in subs)
        return (f'<section style="margin:0 0 28px;padding:26px 22px 22px;background-color:{t["dark"]};'
                f'border-radius:8px;">{chip}'
                f'<p style="margin:0;font-size:{fs + 7}px;line-height:1.4;font-weight:bold;color:#ffffff;">{title}</p>'
                f'{sub}<p style="margin:18px 0 0;font-size:0;line-height:0;">'
                f'<span style="display:inline-block;width:36px;height:3px;background-color:{t["primary"]};"></span>'
                f'<span style="display:inline-block;width:8px;height:3px;margin-left:6px;'
                f'background-color:{t["primary_line"]};"></span></p></section>')

    if style == "block":
        fg = t["on_primary"]
        sub = "".join(f'<p style="margin:8px 0 0;font-size:{fs - 1}px;line-height:1.7;color:{fg};">'
                      f'{inline(s, t)}</p>' for s in subs)
        kick = (f'<p style="margin:0 0 10px;font-size:13px;font-weight:bold;letter-spacing:2px;color:{fg};">'
                f'{kicker}</p>') if kicker else ""
        return (f'<section style="margin:0 0 28px;padding:24px 20px;background-color:{t["primary"]};'
                f'border-radius:8px;text-align:center;">{kick}'
                f'<p style="margin:0;font-size:{fs + 7}px;line-height:1.4;font-weight:bold;color:{fg};">{title}</p>'
                f'{sub}</section>')

    if style == "rule":
        sub = "".join(f'<p style="margin:10px 0 0;font-size:{fs - 1}px;line-height:1.75;color:{t["text_muted"]};">'
                      f'{inline(s, t)}</p>' for s in subs)
        kick = (f'<p style="margin:0 0 12px;font-size:13px;letter-spacing:3px;color:{t["primary_ink"]};'
                f'font-weight:bold;">{kicker}</p>') if kicker else ""
        return (f'<section style="margin:0 0 30px;padding:18px 0 20px;border-top:3px solid {t["heading"]};'
                f'border-bottom:1px solid {t["divider"]};text-align:center;">{kick}'
                f'<p style="margin:0;font-size:{fs + 8}px;line-height:1.35;font-weight:bold;color:{t["heading"]};">'
                f'{title}</p>{sub}</section>')

    if style == "ornament":
        orn = t["ornament"]
        sub = "".join(f'<p style="margin:10px 0 0;font-size:{fs - 1}px;line-height:1.9;letter-spacing:1px;'
                      f'color:{t["text_muted"]};">{inline(s, t)}</p>' for s in subs)
        kick = (f'<p style="margin:0 0 12px;font-size:13px;letter-spacing:4px;color:{t["primary_ink"]};">'
                f'{kicker}</p>') if kicker else ""
        return (f'<section style="margin:0 0 30px;padding:20px 12px;text-align:center;">'
                f'<p style="margin:0 0 12px;font-size:12px;color:{t["accent_ink"]};">{orn}</p>{kick}'
                f'<p style="margin:0;font-size:{fs + 6}px;line-height:1.5;letter-spacing:3px;font-weight:bold;'
                f'color:{t["heading"]};">{title}</p>{sub}'
                f'<p style="margin:12px 0 0;font-size:12px;color:{t["accent_ink"]};">{orn}</p></section>')

    sub = "".join(f'<p style="margin:8px 0 0;font-size:{fs - 1}px;line-height:1.75;color:{t["text_muted"]};">'
                  f'{inline(s, t)}</p>' for s in subs)
    kick = (f'<p style="margin:0 0 10px;font-size:13px;font-weight:bold;letter-spacing:1px;'
            f'color:{t["primary_ink"]};">{kicker}</p>') if kicker else ""
    return (f'<section style="margin:0 0 28px;padding:22px 20px;background-color:{t["primary_soft"]};'
            f'border-left:4px solid {t["primary"]};border-radius:6px;">{kick}'
            f'<p style="margin:0;font-size:{fs + 6}px;line-height:1.4;font-weight:bold;color:{t["heading"]};">{title}</p>'
            f'{sub}</section>')  # soft


def render_code(block: dict, t: dict) -> str:
    """命令/代码块：arg 为标签；以 $ 开头的行渲染为命令提示符。"""
    label = html.escape(block["arg"], quote=False)
    rows = block["text"].split("\n") if block["text"] else []
    terminal = t["c"]["code"] == "terminal"
    fg = "#e6ebf2" if terminal else t["text"]
    prompt = t["primary_line"] if terminal else t["primary_ink"]
    lines = []
    for row in rows:
        if row.startswith("$ "):
            body = f'<span style="color:{prompt};">$&nbsp;</span>{html.escape(row[2:], quote=False)}'
        else:
            body = html.escape(row, quote=False) or "&nbsp;"
        lines.append(f'<p style="margin:0;font-family:{MONO};font-size:13px;line-height:1.7;color:{fg};'
                     f'white-space:pre-wrap;word-break:break-all;">{body}</p>')
    if terminal:
        dots = "".join(f'<span style="display:inline-block;width:8px;height:8px;margin-right:6px;'
                       f'border-radius:50%;background-color:{c};"></span>' for c in ("#5b6475", "#7b8495", "#9ba3b2"))
        head = (f'<p style="margin:0 0 12px;font-size:12px;line-height:1;color:#9ba3b2;">{dots}'
                f'<span style="margin-left:6px;vertical-align:top;">{label}</span></p>')
        return (f'<section style="margin:22px 0;padding:14px 16px 16px;background-color:{t["dark"]};'
                f'border-radius:8px;">{head}{"".join(lines)}</section>')
    head = (f'<p style="margin:0 0 8px;font-size:12px;font-weight:bold;letter-spacing:1px;'
            f'color:{t["primary_ink"]};">{label}</p>') if label else ""
    return (f'<section style="margin:22px 0;padding:14px 16px;background-color:{t["bg_soft"]};'
            f'border-left:3px solid {t["primary"]};border-radius:6px;">{head}{"".join(lines)}</section>')


def render_steps(block: dict, t: dict) -> str:
    """步骤条：每行一步，写成「标题 | 说明」。"""
    fs, lh = t["font_size"], t["line_height"]
    steps = [split_pair(ln) for ln in block["text"].split("\n") if ln.strip()]
    label = (f'<p style="margin:0 0 14px;font-size:13px;font-weight:bold;letter-spacing:1px;'
             f'color:{t["primary_ink"]};">{inline(block["arg"], t)}</p>') if block["arg"] else ""
    items = []
    if t["c"]["steps"] == "cards":
        for idx, (title, desc) in enumerate(steps, 1):
            items.append(
                f'<section style="margin:0 0 10px;padding:12px 14px;background-color:{t["primary_soft"]};'
                f'border-radius:8px;"><p style="margin:0;font-size:{fs}px;line-height:1.6;font-weight:bold;'
                f'color:{t["heading"]};"><span style="margin-right:10px;font-size:20px;font-family:Georgia,serif;'
                f'color:{t["primary_ink"]};">{idx:02d}</span>{inline(title, t)}</p>'
                + (f'<p style="margin:4px 0 0;font-size:{fs - 1}px;line-height:{lh};color:{t["text_muted"]};">'
                   f'{inline(desc, t)}</p>' if desc else "") + "</section>")
        return f'<section style="margin:24px 0;">{label}{"".join(items)}</section>'
    for idx, (title, desc) in enumerate(steps, 1):
        last = idx == len(steps)
        items.append(
            f'<section style="margin:0;padding:0 0 {0 if last else 18}px 18px;'
            f'border-left:2px solid {"transparent" if last else t["primary_line"]};">'
            f'<p style="margin:0 0 4px -31px;font-size:{fs}px;line-height:1.6;font-weight:bold;color:{t["heading"]};">'
            f'<span style="display:inline-block;width:24px;height:24px;margin-right:10px;line-height:24px;'
            f'text-align:center;font-size:13px;border-radius:50%;background-color:{t["primary"]};'
            f'color:{t["on_primary"]};">{idx}</span>{inline(title, t)}</p>'
            + (f'<p style="margin:0;font-size:{fs - 1}px;line-height:{lh};color:{t["text_muted"]};">'
               f'{inline(desc, t)}</p>' if desc else "") + "</section>")
    return f'<section style="margin:24px 0 24px 12px;">{label}{"".join(items)}</section>'


def render_callout(block: dict, t: dict) -> str:
    """提示卡 :::tip / 注意卡 :::warn；arg 可改标签文字。"""
    fs, lh = t["font_size"], t["line_height"]
    warn = block["type"] == "warn"
    label = block["arg"] or ("注意" if warn else "提示")
    fg = "#8a6d3b" if warn else t["primary_ink"]
    text_fg = fg if warn else t["text"]
    paras = "".join(f'<p style="margin:6px 0 0;font-size:{fs - 1}px;line-height:{lh};color:{text_fg};">'
                    f'{inline(p, t)}</p>' for p in block["text"].split("\n") if p.strip())
    if t["c"]["callout"] == "line":
        box = f'border-left:3px solid {"#d9a441" if warn else t["primary"]};padding:4px 0 4px 14px;'
    else:
        box = f'padding:14px 16px;background-color:{"#fff8e6" if warn else t["primary_soft"]};border-radius:6px;'
    return (f'<section style="margin:22px 0;{box}">'
            f'<p style="margin:0;font-size:14px;font-weight:bold;color:{fg};">{html.escape(label, quote=False)}</p>'
            f'{paras}</section>')


def render_follow(block: dict, t: dict) -> str:
    """文末关注卡：arg 为「账号名 | 一句理由」。"""
    name, reason = split_pair(block["arg"])
    extra = [ln for ln in block["text"].split("\n") if ln.strip()]
    texts = ([reason] if reason else []) + extra
    style = t["c"]["follow"]
    if style == "minimal":
        lines = "".join(f'<p style="margin:6px 0 0;font-size:14px;line-height:1.7;color:{t["text_muted"]};">'
                        f'{inline(x, t)}</p>' for x in texts)
        return (f'<section style="margin:36px 0 12px;padding:18px 0;border-top:1px solid {t["divider"]};'
                f'border-bottom:1px solid {t["divider"]};text-align:center;">'
                f'<p style="margin:0;font-size:{t["font_size"]}px;font-weight:bold;letter-spacing:1px;'
                f'color:{t["primary_ink"]};">关注「{inline(name, t)}」</p>{lines}</section>')
    if style == "card":
        bg, title_fg, fg, top = t["primary_soft"], t["primary_ink"], t["text_muted"], f'border-top:3px solid {t["primary"]};'
    else:  # echo：与刊头同外观
        top = ""
        mast = t["c"]["masthead"]
        if mast == "dark":
            bg, title_fg, fg = t["dark"], "#ffffff", "#c9d3e3"
        elif mast == "block":
            bg, title_fg, fg = t["primary"], t["on_primary"], t["on_primary"]
        else:
            bg, title_fg, fg = t["primary_soft"], t["primary_ink"], t["text_muted"]
    lines = "".join(f'<p style="margin:6px 0 0;font-size:14px;line-height:1.7;color:{fg};">{inline(x, t)}</p>'
                    for x in texts)
    return (f'<section style="margin:36px 0 12px;padding:22px 18px;background-color:{bg};{top}'
            f'border-radius:8px;text-align:center;">'
            f'<p style="margin:0;font-size:{t["font_size"] + 1}px;font-weight:bold;color:{title_fg};">'
            f'关注「{inline(name, t)}」</p>{lines}</section>')


def render_ending(t: dict) -> str:
    style = t["c"]["ending"]
    if style == "end":
        return (f'<p style="margin:36px 0 12px;text-align:center;font-size:12px;letter-spacing:4px;'
                f'color:{t["text_muted"]};">— END —</p>')
    if style == "sign":
        line = (f'<span style="display:inline-block;width:60px;height:1px;vertical-align:middle;'
                f'background-color:{t["primary_line"]};"></span>')
        return (f'<p style="margin:40px 0 12px;text-align:center;font-size:12px;line-height:1;letter-spacing:4px;'
                f'color:{t["primary_ink"]};">{line}<span style="margin:0 12px;font-weight:bold;">END</span>{line}</p>')
    if style == "ornament":
        orn = t["ornament"]
        return (f'<p style="margin:36px 0 12px;text-align:center;font-size:12px;letter-spacing:6px;'
                f'color:{t["accent_ink"]};">{orn} {orn} {orn}</p>')
    return ""


def render(blocks: list[dict], t: dict, caption: bool = True) -> tuple[str, list[str]]:
    fs, lh, gap = t["font_size"], t["line_height"], t["para_gap"]
    h2_index = 0
    seen_paragraph = False
    body: list[str] = []
    has_masthead = any(b["type"] == "masthead" for b in blocks)
    ending = render_ending(t)

    for block in blocks:
        kind = block["type"]
        if kind == "h" and block["level"] == 1:
            if not has_masthead:  # 有刊头时标题由刊头承担，正文不再重复
                body.append(f'<h1 style="margin:0 0 24px;font-size:{fs + 6}px;line-height:1.4;font-weight:bold;'
                            f'color:{t["heading"]};text-align:center;">{inline(block["text"], t)}</h1>')
        elif kind == "h" and block["level"] == 2:
            h2_index += 1
            body.append(render_h2(block["text"], h2_index, t))
        elif kind == "h":
            body.append(render_h3(block["text"], t))
        elif kind == "p":
            if not seen_paragraph:  # 首段即导语
                seen_paragraph = True
                body.append(render_lead(block["text"], t))
            else:
                body.append(f'<p style="margin:0 0 {gap}px;text-align:justify;font-size:{fs}px;'
                            f'line-height:{lh};">{inline(block["text"], t)}</p>')
        elif kind in ("ul", "ol"):
            items = "".join(f'<li style="margin:0 0 10px;line-height:{lh};font-size:{fs}px;">'
                            f'{inline(item, t)}</li>' for item in block["items"])
            body.append(f'<{kind} style="margin:0 0 {gap}px;padding-left:{22 if kind == "ul" else 24}px;'
                        f'color:{t["text"]};">{items}</{kind}>')
        elif kind == "quote":
            body.append(render_quote(block["text"], t))
        elif kind == "hr":
            body.append(render_divider(t))
        elif kind == "img":
            body.append(render_figure(block, t, caption))
        elif kind == "masthead":
            body.append(render_masthead(block, t))
        elif kind == "code":
            body.append(render_code(block, t))
        elif kind == "steps":
            body.append(render_steps(block, t))
        elif kind in ("tip", "warn"):
            body.append(render_callout(block, t))
        elif kind == "follow":
            if ending:  # 收尾标记放在关注卡之前
                body.append(ending)
                ending = ""
            body.append(render_follow(block, t))
        elif kind == "html":
            body.append(block["text"])  # Agent 手写的组件原样输出；合规由 check_html.py 把关
        elif kind == "card":
            body.append(render_card(block["text"], t, block.get("arg", "")))
        elif kind == "points":
            body.append(render_points(block, t))
        elif kind == "compare":
            body.append(render_compare(block, t))
        elif kind == "cta":
            body.append(render_cta(block["text"] or block.get("arg", ""), t))
        elif kind == "stat":
            body.append(render_stat(block["arg"], block["text"], t))
        elif kind == "note":
            body.append(f'<p style="margin:0 0 {gap}px;font-size:{fs - 1}px;line-height:{lh};'
                        f'color:{t["text_muted"]};">{inline(block["text"], t)}</p>')
    body.append(ending)

    links = re.findall(r"\]\((https?://[^)\s]+)\)", "\n".join(b.get("text", "") for b in blocks))
    wrapper = (f'<section style="max-width:100%;padding:0 16px;box-sizing:border-box;color:{t["text"]};'
               f'font-size:{fs}px;line-height:{lh};letter-spacing:{t["letter_spacing"]};">'
               + "".join(body) + "</section>")
    return wrapper, links


# ---------------------------------------------------------------- 方案备选、对比页与样式库

PAGE_CSS = """
  body { margin:0;padding:32px 24px;background:#f2f3f5;color:#222;
         font-family:-apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif; }
  h1 { font-size:24px;margin:0 0 8px; } h2.sec { font-size:19px;margin:36px 0 6px; }
  .intro { margin:0 0 24px;color:#666;font-size:14px;line-height:1.7;max-width:820px; }
  .grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:20px; }
  .box { background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px; }
  .box h3 { font-size:16px;margin:0 0 6px; } .box h3 code, .tag { font-size:12px;color:#8a8f98;
            background:#f4f5f7;padding:2px 6px;border-radius:4px;font-weight:normal; }
  .meta { margin:0 0 10px;color:#666;font-size:12.5px;line-height:1.7; }
  .phone { background:#fff;border:1px solid #eceef1;border-radius:10px;padding:16px 0;max-width:400px; }
  .sw { display:inline-block;width:22px;height:22px;border-radius:4px;vertical-align:middle;margin-right:4px;
        border:1px solid rgba(0,0,0,.06); }
  .pal { display:inline-block;width:230px;margin:0 12px 12px 0;font-size:12.5px;line-height:1.6;color:#555;
         vertical-align:top; }
  pre { background:#f6f7f9;border-radius:6px;padding:8px 10px;font-size:11.5px;overflow:auto;max-height:160px; }
  footer { margin-top:28px;color:#8a8f98;font-size:12.5px;line-height:1.7; }
"""


def page(title: str, intro: str, body: str) -> str:
    return (f'<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8" />\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1" />\n<title>{title}</title>\n'
            f'<style>{PAGE_CSS}</style>\n</head>\n<body>\n<h1>{title}</h1>\n<p class="intro">{intro}</p>\n{body}\n'
            f'<footer>本页仅为本地预览；实际效果以微信内为准，微信会改写部分内联样式。</footer>\n</body>\n</html>\n')


GALLERY_SAMPLES = {
    "masthead": [{"type": "masthead", "arg": "栏目名 · 本期", "text": "一句话说清这篇讲什么\n副题：给读者一个读下去的理由"}],
    "h2": [{"type": "h", "level": 2, "text": "二级标题示例"}],
    "h3": [{"type": "h", "level": 3, "text": "三级标题示例"}],
    "lead": [{"type": "p", "text": "导语示例：首段两三句说清读者为什么要读下去。"}],
    "quote": [{"type": "quote", "text": "引语示例：一句值得被单独拎出来的话。"}],
    "card": [{"type": "card", "arg": "一句话结论", "text": "结论卡示例：把全文最该被记住的一句话放在这里。"}],
    "points": [{"type": "points", "arg": "本文要点", "text": "第一条要点\n第二条要点，==重点高亮==\n第三条要点"}],
    "compare": [{"type": "compare", "arg": "很多人以为 | 实际上", "text": "旧认知一 | 新事实一\n旧认知二 | 新事实二"}],
    "cta": [{"type": "cta", "text": "回复关键词，领取完整清单。"}],
    "stat": [{"type": "stat", "arg": "128 | 数字块示例注解", "text": ""}],
    "divider": [{"type": "hr"}],
    "figure": [{"type": "img", "alt": "图注示例",
                "src": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='170'>"
                       "<rect width='400' height='170' fill='%23d9dde3'/></svg>"}],
    "code": [{"type": "code", "arg": "在终端运行", "text": "$ npx example-cli init\n完成"}],
    "steps": [{"type": "steps", "arg": "三步上手", "text": "准备 | 一句话说明\n执行 | 照做的动作\n检查 | 做对了是什么样"}],
    "callout": [{"type": "tip", "arg": "", "text": "提示卡示例：容易忽略但很有用的一句话。"}],
    "follow": [{"type": "follow", "arg": "账号名 | 关注能得到什么", "text": ""}],
    "ending": [],
}


def build_gallery(lib: dict, out: Path, design: dict) -> None:
    """样式库预览：每个组件的全部样式（用同一套配色）+ 全部选题配色 + 全部调性。"""
    sections = []
    for slot, spec in lib["components"].items():
        boxes = []
        for var in variants(lib, slot):
            d = json.loads(json.dumps(design))
            d["components"][slot] = var
            if slot != "ending":
                d["components"]["ending"] = "none"
            if slot == "h2":
                d["numbered"] = False
            t = design_tokens(d, lib)
            sample = GALLERY_SAMPLES[slot]
            if slot == "lead":
                sample = sample + [{"type": "p", "text": "正文段落对照。"}]
            rendered, _ = render(sample, t)
            boxes.append(f'<section class="box"><h3>{html.escape(spec[var])} <code>{slot}={var}</code></h3>'
                         f'<div class="phone">{rendered}</div></section>')
        sections.append(f'<h2 class="sec">{html.escape(spec["_slot"])}</h2><div class="grid">{"".join(boxes)}</div>')

    pals = "".join(
        f'<span class="pal"><span class="sw" style="background:{p["primary"]}"></span>'
        + (f'<span class="sw" style="background:{p["accent"]}"></span>' if p.get("accent") else "")
        + f'<b>{html.escape(p["name"])}</b> <span class="tag">{p["id"]}</span><br>'
          f'{html.escape("、".join(p["topics"][:6]))}</span>' for p in lib["palettes"])
    moods = "".join(f'<span class="pal"><b>{html.escape(m["name"])}</b> <span class="tag">{m["id"]}</span><br>'
                    f'{html.escape(m["desc"])}</span>' for m in lib["moods"])
    intro = (f"类似编辑器样式中心：每个组件有几种样式，按选题自由组合，不绑定成套模版。下面用「{html.escape(design['name'])}」"
             f"的配色展示；换配色用 --palette 或 --primary 重新生成。选中某个样式时把下方的 "
             f"<code>组件=样式</code> 写进方案的 components，或用 --set 传入。")
    body = (f'<h2 class="sec">选题配色</h2><div>{pals}</div><h2 class="sec">调性（只决定字号节奏与组件倾向）</h2>'
            f'<div>{moods}</div>' + "".join(sections))
    out.write_text(page("公众号排版样式库", intro, body), encoding="utf-8")


SAMPLE_TEXT = "## 示例\n\n示例正文。"


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="公众号排版设计渲染器（按选题组合设计方案 → 渲染微信安全 HTML）")
    ap.add_argument("input", nargs="?", type=Path, help="Markdown 正文文件；用 - 读标准输入")
    ap.add_argument("--design", type=Path, help="设计方案 JSON（可只写部分字段，其余自动补全）")
    ap.add_argument("--hint", default="", help="用户的风格原话，如「国风 高级感」，参与调性与配色判断")
    ap.add_argument("--mood", help="指定调性 id，如 tech / warm / oriental")
    ap.add_argument("--palette", help="指定选题配色 id，如 autumn / tech-blue")
    ap.add_argument("--primary", help="品牌主色 #RRGGBB（覆盖配色，所有组件一起换色）")
    ap.add_argument("--accent", help="强调色 #RRGGBB（可选，默认同主色）")
    ap.add_argument("--set", dest="sets", help="逐个指定组件样式，如 h2=part,figure=round")
    ap.add_argument("--numbered", action="store_true", help="给不带序号的标题样式加 01/02 编号")
    ap.add_argument("--density", choices=sorted(DENSITY), help="阅读密度：large 大字宽松 / standard / compact 紧凑")
    ap.add_argument("--auto", action="store_true", help="只输出设计方案 JSON（含理由），不渲染")
    ap.add_argument("--gallery", type=Path, help="生成样式库预览页（全部组件样式 + 全部配色）")
    ap.add_argument("--list", action="store_true", help="列出调性、配色与组件样式")
    ap.add_argument("--save-design", type=Path, help="把最终设计方案写入 JSON，便于复用与改版")
    ap.add_argument("--print-tokens", action="store_true", help="打印最终 token JSON（手写组件取色用）")
    ap.add_argument("--no-caption", action="store_true", help="图片下方不生成图注")
    ap.add_argument("-o", "--out", type=Path, help="HTML 输出路径，默认打印到标准输出")
    args = ap.parse_args()

    lib = load_library()

    if args.list:
        print("调性（只决定字号节奏与组件倾向）：")
        for m in lib["moods"]:
            print(f"  {m['id']:10s} {m['name']:6s} {m['desc']}")
        print("\n选题配色：")
        for p in lib["palettes"]:
            print(f"  {p['id']:17s} {p['name']:8s} {p['primary']}  {'、'.join(p['topics'][:6])}")
        print("\n组件样式（--set 组件=样式）：")
        for slot, spec in lib["components"].items():
            print(f"  {slot:9s} {spec['_slot']}：" + " / ".join(variants(lib, slot)))
        return 0

    spec = json.loads(args.design.read_text(encoding="utf-8")) if args.design else {}
    spec.pop("reasons", None)
    for key in ("mood", "palette", "density"):
        if getattr(args, key):
            spec[key] = getattr(args, key)
    if args.palette:
        spec.pop("colors", None)
    if args.primary:
        spec["colors"] = {"primary": args.primary, "accent": args.accent or args.primary}
    elif args.accent:
        spec.setdefault("colors", {})["accent"] = args.accent
    if args.sets:
        spec["components"] = {**spec.get("components", {}), **parse_sets(args.sets)}
    if args.numbered:
        spec["numbered"] = True

    if args.gallery:
        text = args.input.read_text(encoding="utf-8") if args.input else SAMPLE_TEXT
        build_gallery(lib, args.gallery, resolve_design(text, lib, spec, args.hint))
        print(f"样式库预览页已生成：{args.gallery}")
        return 0

    if args.input is None:
        ap.error("需要提供正文文件（或用 --list / --gallery）")
    text = sys.stdin.read() if str(args.input) == "-" else args.input.read_text(encoding="utf-8")

    design = resolve_design(text, lib, spec, args.hint)
    if args.auto:
        print(json.dumps(design, ensure_ascii=False, indent=2))
        return 0

    tokens = design_tokens(design, lib)
    print(f"设计方案：{design['name']}（主色 {tokens['primary']}）", file=sys.stderr)
    for why in design["reasons"]:
        print(f"  - {why}", file=sys.stderr)
    if contrast(tokens["primary"], tokens["on_primary"]) < 4.5:
        print("提示：主色上的文字对比度偏低（已自动选黑/白字）；若品牌规范要求白字，请换更深的主色。", file=sys.stderr)
    if args.save_design:
        args.save_design.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.print_tokens:
        print(json.dumps({k: v for k, v in tokens.items() if k != "c"}, ensure_ascii=False, indent=2))

    html_out, links = render(parse_markdown(text), tokens, caption=not args.no_caption)
    if args.out:
        args.out.write_text(html_out, encoding="utf-8")
        print(f"已渲染：{args.out}（{design['name']}，{len(html_out)} 字节）")
    else:
        print(html_out)
    if links:
        print("\n注意：正文含外链，公众号正文外链通常不可点击，需单独处理：", file=sys.stderr)
        for url in links:
            print(f"  {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
