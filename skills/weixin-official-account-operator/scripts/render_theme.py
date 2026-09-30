#!/usr/bin/env python3
"""公众号主题风格渲染器：按主题把 Markdown 正文渲染成微信安全的内联样式 HTML。

三种用法：
  1) 看主题库与自动推荐：--list / --suggest 内容.md
  2) 渲染正文：render_theme.py 内容.md --theme tech -o out.html
  3) 生成主题对比页：--showcase theme-showcase.html

主题 token 单一数据源是 ../assets/themes.json。支持用品牌色派生定制主题
（--primary，可选 --accent），派生时自动推导浅色底/描边并按对比度选择 CTA 文字色。

仅依赖标准库，无第三方包。用法示例见文件末尾 --help。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

THEMES_PATH = Path(__file__).resolve().parent.parent / "assets" / "themes.json"

FENCED = re.compile(r"^:::(card|cta|stat|note)\s*(.*)$")
IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
HR = re.compile(r"^(-{3,}|\*{3,})$")


# ---------------------------------------------------------------- 主题加载

def load_themes(path: Path = THEMES_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def find_theme(bundle: dict, theme_id: str) -> dict:
    for theme in bundle["themes"]:
        if theme["id"] == theme_id:
            return theme
    raise SystemExit(f"未找到主题 {theme_id}；用 --list 查看可用主题")


# ---------------------------------------------------------------- 颜色工具

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise SystemExit(f"颜色格式无效：{value}（应为 #RRGGBB）")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


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


# ---------------------------------------------------------------- 主题派生

def derive_theme(base: dict, primary: str, accent: str | None, name: str | None) -> dict:
    """用品牌主色从基准主题派生一套定制 token，保留版式骨架只换皮肤。"""
    tokens = json.loads(json.dumps(base["tokens"]))  # 深拷贝
    primary = rgb_to_hex(hex_to_rgb(primary))
    accent = rgb_to_hex(hex_to_rgb(accent)) if accent else primary

    tokens["primary"] = primary
    tokens["accent"] = accent
    tokens["primary_soft"] = mix(primary, "#ffffff", 0.88)
    tokens["primary_line"] = mix(primary, "#ffffff", 0.62)
    tokens["h3"]["color"] = primary
    tokens["stat"]["color"] = accent
    tokens["card"]["bar"] = primary
    tokens["quote"]["bar"] = tokens["primary_line"]
    tokens["cta"]["bg"] = primary

    if tokens["h2"].get("style") == "block":
        tokens["h2"]["color"] = readable_text(primary)
    elif tokens["h2"].get("style") in ("bar", "number"):
        tokens["h2"]["color"] = mix(primary, "#111111", 0.35)
    tokens["cta"]["text"] = readable_text(primary)

    derived = dict(base)
    derived["id"] = f"{base['id']}-custom"
    derived["name"] = name or f"{base['name']}（定制 {primary}）"
    derived["tagline"] = f"由 {base['name']} 派生，主色 {primary}"
    derived["tokens"] = tokens
    derived["derived_from"] = base["id"]
    return derived


# ---------------------------------------------------------------- 自动推荐

def score_themes(text: str, bundle: dict) -> list[dict]:
    """按内容信号词与结构特征给主题打分，返回降序结果。"""
    low = text.lower()
    intent = bundle.get("intent_words", {})
    results = []

    for theme in bundle["themes"]:
        hits = [kw for kw in theme["signals"] if kw.lower() in low]
        score = min(len(hits) * 3, 24)  # 领域关键词优先于下面通用的结构特征
        reasons = [f"命中「{h}」" for h in hits[:4]]

        for word, target in intent.items():
            if word in text and target == theme["id"]:
                score += 8
                reasons.insert(0, f"明确要求「{word}」")

        # 结构特征：只在信号词不足以判断时补充，避免关键词刷分
        if re.search(r"第[一二三四五六七八九十\d]+\s*[步章节]|步骤\s*\d", text):
            if theme["id"] == "academic":
                score += 4
                reasons.append("含分步骤结构")
        if len(re.findall(r"\d+(\.\d+)?%", text)) >= 3:
            if theme["id"] in ("academic", "professional"):
                score += 3
                reasons.append("含多组百分比数据")
        if re.search(r"限时|截止|报名|席位|倒计时|优惠|元/年", text):
            if theme["id"] == "vibrant":
                score += 6
                reasons.append("含活动/时限表述")
        if len(re.findall(r"[“”\"]", text)) >= 4:
            if theme["id"] in ("warm", "magazine"):
                score += 3
                reasons.append("含大量引语/对话")
        if re.search(r"节气|非遗|传统|文化|美学|东方|中式", text):
            if theme["id"] == "oriental":
                score += 5
                reasons.append("含传统文化意象")

        paras = [p for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 30]
        if paras and sum(len(p) for p in paras) / len(paras) > 120:
            if theme["id"] == "magazine":
                score += 3
                reasons.append("长段落为主，偏深度阅读")

        results.append({
            "id": theme["id"], "name": theme["name"], "tagline": theme["tagline"],
            "score": score, "reasons": reasons[:5],
        })

    return sorted(results, key=lambda r: (-r["score"], r["id"]))


# ---------------------------------------------------------------- 内容解析

def inline(text: str, tokens: dict) -> str:
    """转义后应用行内样式：加粗、斜体、代码、链接。"""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`",
                 lambda m: f'<code style="padding:2px 6px;background-color:{tokens["bg_soft"]};'
                           f'color:{tokens["primary"]};border-radius:3px;font-size:0.92em;">{m.group(1)}</code>',
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
        raw = lines[i].rstrip()
        line = raw.strip()

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
                body.append(lines[i].strip())
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
            level = len(heading.group(1))
            blocks.append({"type": "h", "level": level, "text": heading.group(2).strip()})
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

        if re.match(r"^[-*]\s+", line):
            flush()
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "ul", "items": items})
            continue

        if re.match(r"^\d+[.)]\s+", line):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+[.)]\s+", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "ol", "items": items})
            continue

        paragraph.append(line)
        i += 1

    flush()
    return blocks


# ---------------------------------------------------------------- 渲染

def style_of(parts: list[str]) -> str:
    return ";".join(p for p in parts if p) + ";"


def render(blocks: list[dict], theme: dict, caption: bool = True) -> str:
    t = theme["tokens"]
    fs, lh, gap = t["font_size"], t["line_height"], t["para_gap"]
    h2_index = 0
    seen_paragraph = False
    links: list[str] = []
    body: list[str] = []

    for block in blocks:
        kind = block["type"]

        if kind == "h" and block["level"] == 1:
            body.append(
                f'<h1 style="margin:0 0 24px;font-size:{fs + 6}px;line-height:1.4;'
                f'font-weight:bold;color:{t["text"]};text-align:center;">'
                f'{inline(block["text"], t)}</h1>')
            continue

        if kind == "h" and block["level"] == 2:
            h2_index += 1
            h2 = t["h2"]
            shared = f'margin:32px 0 16px;font-size:{h2["size"]}px;line-height:1.4;font-weight:{h2.get("weight", "bold")}'
            style = h2.get("style", "bar")
            prefix = f'<span style="color:{t["primary"]};margin-right:8px;">{h2_index:02d}</span>' if t.get("numbered") else ""

            if style == "block":
                body.append(
                    f'<h2 style="{shared};padding:10px 14px;background-color:{t["primary"]};'
                    f'color:{h2.get("color", "#ffffff")};border-radius:{h2.get("radius", 4)}px;">'
                    f'{prefix}{inline(block["text"], t)}</h2>')
            elif style == "underline":
                body.append(
                    f'<h2 style="{shared};padding-bottom:8px;color:{h2["color"]};'
                    f'border-bottom:{h2.get("bar_width", 2)}px solid {t["primary"]};">'
                    f'{prefix}{inline(block["text"], t)}</h2>')
            elif style == "center":
                body.append(
                    f'<h2 style="{shared};color:{h2["color"]};text-align:center;padding:14px 0;'
                    f'border-top:1px solid {t["divider"]};border-bottom:1px solid {t["divider"]};">'
                    f'{prefix}{inline(block["text"], t)}</h2>')
            else:  # bar
                body.append(
                    f'<h2 style="{shared};color:{h2["color"]};padding-left:12px;'
                    f'border-left:{h2.get("bar_width", 4)}px solid {t["primary"]};">'
                    f'{prefix}{inline(block["text"], t)}</h2>')
            continue

        if kind == "h" and block["level"] == 3:
            body.append(
                f'<h3 style="margin:26px 0 12px;font-size:{t["h3"]["size"]}px;line-height:1.5;'
                f'font-weight:bold;color:{t["h3"]["color"]};">{inline(block["text"], t)}</h3>')
            continue

        if kind == "p":
            if not seen_paragraph:  # 首段即导语
                seen_paragraph = True
                lead = t["lead"]
                body.append(
                    f'<p style="margin:0 0 {gap + 4}px;color:{lead["color"]};'
                    f'font-weight:{"bold" if lead.get("bold") else "normal"};'
                    f'font-size:{fs}px;line-height:{lh};">{inline(block["text"], t)}</p>')
            else:
                body.append(
                    f'<p style="margin:0 0 {gap}px;text-align:justify;font-size:{fs}px;'
                    f'line-height:{lh};">{inline(block["text"], t)}</p>')
            continue

        if kind == "ul":
            items = "".join(
                f'<li style="margin:0 0 10px;line-height:{lh};font-size:{fs}px;">'
                f'{inline(item, t)}</li>' for item in block["items"])
            body.append(
                f'<ul style="margin:0 0 {gap}px;padding-left:22px;color:{t["text"]};">{items}</ul>')
            continue

        if kind == "ol":
            items = "".join(
                f'<li style="margin:0 0 10px;line-height:{lh};font-size:{fs}px;">'
                f'{inline(item, t)}</li>' for item in block["items"])
            body.append(
                f'<ol style="margin:0 0 {gap}px;padding-left:24px;color:{t["text"]};">{items}</ol>')
            continue

        if kind == "quote":
            q = t["quote"]
            italic = "font-style:italic;" if q.get("italic") else ""
            body.append(
                f'<blockquote style="margin:24px 0;padding:14px 16px;background-color:{q["bg"]};'
                f'border-left:{q.get("bar_width", 3)}px solid {q["bar"]};color:{q["text"]};'
                f'font-size:{fs}px;line-height:{lh};{italic}">{inline(block["text"], t)}</blockquote>')
            continue

        if kind == "hr":
            style = t.get("divider_style", "line")
            if style == "ornament":
                body.append(
                    f'<p style="margin:30px 0;text-align:center;color:{t["primary"]};'
                    f'font-size:12px;letter-spacing:6px;">{t.get("ornament") or "◆ ◆ ◆"}</p>')
            elif style == "dots":
                body.append(
                    f'<p style="margin:30px 0;text-align:center;color:{t["divider"]};'
                    f'font-size:14px;letter-spacing:8px;">• • •</p>')
            else:
                body.append(
                    f'<section style="margin:30px 0;height:1px;line-height:1px;font-size:0;'
                    f'background-color:{t["divider"]};">&nbsp;</section>')
            continue

        if kind == "img":
            img = t["image"]
            radius = f'border-radius:{img["radius"]}px;' if img.get("radius") else ""
            body.append(
                f'<img src="{html.escape(block["src"], quote=True)}" '
                f'alt="{html.escape(block["alt"], quote=True)}" '
                f'style="display:block;width:100%;height:auto;margin:24px auto;{radius}" />')
            if caption and block["alt"]:
                body.append(
                    f'<p style="margin:8px 0 24px;text-align:center;font-size:13px;'
                    f'color:{img["caption"]};line-height:1.6;">'
                    f'{html.escape(block["alt"], quote=False)}</p>')
            continue

        if kind == "card":
            c = t["card"]
            inner = "".join(
                f'<p style="margin:0 0 10px;line-height:{lh};font-size:{fs}px;">{inline(p, t)}</p>'
                for p in block["text"].split("\n") if p.strip()) or \
                f'<p style="margin:0;line-height:{lh};">{inline(block["text"], t)}</p>'
            border = f'border:1px solid {c["bar"]};' if c.get("border") else \
                     f'border-left:{c.get("bar_width", 3)}px solid {c["bar"]};'
            body.append(
                f'<section style="margin:24px 0;padding:16px 18px;background-color:{c["bg"]};'
                f'{border}border-radius:{c.get("radius", 6)}px;color:{c.get("text", t["text_muted"])};">'
                f'{inner}</section>')
            continue

        if kind == "cta":
            c = t["cta"]
            text = block["text"] or block.get("arg", "")
            border = f'border:1px solid {t["primary"]};' if c.get("border") else ""
            body.append(
                f'<section style="margin:28px 0;padding:16px 18px;background-color:{c["bg"]};'
                f'{border}border-radius:{c.get("radius", 6)}px;color:{c["text"]};'
                f'font-size:{fs}px;line-height:{lh};text-align:{c.get("align", "left")};'
                f'font-weight:bold;">{inline(text, t)}</section>')
            continue

        if kind == "stat":
            value, _, note = block["arg"].partition("|")
            value = value.strip() or block["text"].strip()
            note = note.strip()
            body.append(
                f'<section style="margin:28px 0;padding:18px 0;text-align:center;">'
                f'<p style="margin:0;font-size:{t["stat"]["size"]}px;font-weight:bold;'
                f'color:{t["stat"]["color"]};line-height:1.2;">{html.escape(value, quote=False)}</p>'
                + (f'<p style="margin:8px 0 0;font-size:13px;color:{t["text_muted"]};'
                   f'line-height:1.6;">{html.escape(note, quote=False)}</p>' if note else "")
                + '</section>')
            continue

        if kind == "note":
            body.append(
                f'<p style="margin:0 0 {gap}px;font-size:{fs - 1}px;line-height:{lh};'
                f'color:{t["text_muted"]};">{inline(block["text"], t)}</p>')
            continue

    for url in re.findall(r"\]\((https?://[^)\s]+)\)", "\n".join(
            b.get("text", "") for b in blocks)):
        links.append(url)

    wrapper = (
        f'<section style="max-width:100%;padding:0 16px;box-sizing:border-box;'
        f'color:{t["text"]};font-size:{fs}px;line-height:{lh};'
        f'letter-spacing:{t.get("letter_spacing", "0.3px")};">'
        + "".join(body) + "</section>"
    )
    return wrapper, links


# ---------------------------------------------------------------- 对比预览页

SAMPLE_MD = """## 为什么这件事现在值得做

这是导语示范段落：用两三句话说清读者为什么要读下去，并与标题承诺保持一致。

这里是正文段落，每段只讲一个观点，用小标题、列表和结论卡提高手机端扫读效率。

## 三个关键判断

1. 第一个判断，配一句可验证的事实或来源。
2. 第二个判断，说明它改变了什么。
3. 第三个判断，落到读者能做的动作上。

- 补充要点一
- 补充要点二

> 引语示范：一句值得被单独拎出来的话。

:::card
重点结论示范：把全文最该被记住的一句话放在这里。
:::

:::stat 128 | 覆盖企业客户数（示范数据）
:::

## 接下来怎么做

结尾段落回到读者视角，给出下一步行动。

:::cta
点击阅读原文，或回复关键词获取完整清单。
:::
"""


def build_showcase(bundle: dict, out: Path) -> None:
    cards = []
    for theme in bundle["themes"]:
        t = theme["tokens"]
        sample, _ = render(parse_markdown(SAMPLE_MD), theme)
        swatches = "".join(
            f'<span style="display:inline-block;width:26px;height:26px;border-radius:4px;'
            f'background-color:{c};margin-right:6px;vertical-align:middle;'
            f'border:1px solid rgba(0,0,0,0.06);"></span>'
            for c in [t["primary"], t["accent"], t["primary_soft"], t["bg_soft"], t["text"]])
        cards.append(f"""
    <section class="theme">
      <header>
        <h2>{html.escape(theme["name"])} <code>{theme["id"]}</code></h2>
        <p class="tagline">{html.escape(theme["tagline"])}</p>
        <p class="meta"><b>适合</b>：{html.escape("、".join(theme["best_for"]))}<br>
        <b>不适合</b>：{html.escape("、".join(theme["avoid_for"]))}</p>
        <div class="swatches">{swatches}
          <span class="token">{t["font_size"]}px / {t["line_height"]} / 段距 {t["para_gap"]}px</span>
        </div>
      </header>
      <div class="phone">{sample}</div>
    </section>""")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>公众号主题风格对比</title>
<style>
  body {{ margin:0;padding:32px 24px;background:#f2f3f5;color:#222;
         font-family:-apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif; }}
  h1 {{ font-size:24px;margin:0 0 8px; }}
  .intro {{ margin:0 0 28px;color:#666;font-size:14px;line-height:1.7;max-width:760px; }}
  .grid {{ display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:24px; }}
  .theme {{ background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px 22px; }}
  .theme h2 {{ font-size:18px;margin:0 0 6px; }}
  .theme h2 code {{ font-size:12px;color:#8a8f98;background:#f4f5f7;
                    padding:2px 6px;border-radius:4px;font-weight:normal; }}
  .tagline {{ margin:0 0 10px;color:#555;font-size:14px; }}
  .meta {{ margin:0 0 12px;color:#777;font-size:12.5px;line-height:1.7; }}
  .swatches {{ margin-bottom:14px; }}
  .token {{ font-size:12px;color:#8a8f98;margin-left:8px; }}
  .phone {{ background:#fafbfc;border:1px solid #eceef1;border-radius:10px;
            padding:18px 0;max-width:420px; }}
  footer {{ margin-top:28px;color:#8a8f98;font-size:12.5px;line-height:1.7; }}
</style>
</head>
<body>
  <h1>公众号主题风格对比</h1>
  <p class="intro">同一段示例内容在 {len(bundle["themes"])} 套主题下的真实排版效果。色块依次为
     主色 / 强调色 / 浅色底 / 卡片底 / 正文色。选定主题后用
     <code>render_theme.py 正文.md --theme &lt;id&gt;</code> 渲染正式稿；
     如需品牌色，加 <code>--primary #RRGGBB</code> 从最接近的主题派生。</p>
  <div class="grid">{"".join(cards)}
  </div>
  <footer>本页仅为本地选型预览；实际效果以微信内为准，微信会改写部分内联样式。</footer>
</body>
</html>
"""
    out.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(
        description="公众号主题风格渲染器（自动推荐主题 → 渲染微信安全 HTML）")
    ap.add_argument("input", nargs="?", type=Path, help="Markdown 正文文件；用 - 读标准输入")
    ap.add_argument("--theme", help="主题 id，如 professional / tech / warm")
    ap.add_argument("--primary", help="品牌主色 #RRGGBB，从基准主题派生定制皮肤")
    ap.add_argument("--accent", help="品牌强调色 #RRGGBB（可选，默认同主色）")
    ap.add_argument("--base", help="派生时使用的基准主题 id（默认取自动推荐第一名）")
    ap.add_argument("--name", help="派生主题的名称")
    ap.add_argument("--suggest", action="store_true", help="只做主题推荐并打印评分，不渲染")
    ap.add_argument("--list", action="store_true", help="列出全部主题")
    ap.add_argument("--print-tokens", action="store_true", help="打印最终主题的 token JSON")
    ap.add_argument("--no-caption", action="store_true", help="图片下方不生成图注")
    ap.add_argument("-o", "--out", type=Path, help="HTML 输出路径，默认打印到标准输出")
    ap.add_argument("--showcase", type=Path, help="生成主题对比预览页到指定路径")
    args = ap.parse_args()

    bundle = load_themes()

    if args.list:
        print(f"{'ID':16s} {'名称':10s} {'字号/行高':>10s}  适用")
        for theme in bundle["themes"]:
            t = theme["tokens"]
            print(f"{theme['id']:16s} {theme['name']:10s} "
                  f"{str(t['font_size']) + '/' + str(t['line_height']):>10s}  "
                  f"{'、'.join(theme['best_for'])}")
        return 0

    if args.showcase:
        build_showcase(bundle, args.showcase)
        print(f"主题对比页已生成：{args.showcase}")
        return 0

    if args.input is None:
        ap.error("需要提供正文文件（或用 --list / --showcase）")

    text = sys.stdin.read() if str(args.input) == "-" else args.input.read_text(encoding="utf-8")

    ranked = score_themes(text, bundle)
    top = ranked[0]

    if args.suggest:
        print(f"{'#':>2s} {'主题':16s} {'名称':10s} {'分':>4s}  依据")
        for idx, item in enumerate(ranked[:5], 1):
            print(f"{idx:>2d} {item['id']:16s} {item['name']:10s} {item['score']:>4d}  "
                  f"{'；'.join(item['reasons']) or '无明显信号'}")
        print(f"\n推荐：{top['id']}（{top['name']}）—— {top['tagline']}")
        return 0

    base_id = args.theme or args.base or top["id"]
    base = find_theme(bundle, base_id)

    if args.theme is None and not args.primary:
        print(f"未指定主题，按内容自动选择：{base['id']}（{base['name']}）；"
              f"依据 {'；'.join(top['reasons']) or '默认兜底'}", file=sys.stderr)
        runners = [r for r in ranked[1:3] if r["score"] > 0]
        if runners:
            print("备选：" + "、".join(f"{r['id']}({r['score']})" for r in runners), file=sys.stderr)

    theme = derive_theme(base, args.primary, args.accent, args.name) if args.primary else base

    if args.primary:
        cta_bg, cta_fg = theme["tokens"]["cta"]["bg"], theme["tokens"]["cta"]["text"]
        ratio = contrast(cta_bg, cta_fg)
        print(f"已派生主题：{theme['name']}（主色 {theme['tokens']['primary']}，"
              f"CTA 对比度 {ratio:.1f}:1）", file=sys.stderr)
        if ratio < 4.5:
            print("提示：主色与 CTA 文字对比度偏低，深色文字已自动启用；"
                  "若品牌规范要求白字，请改用更深的主色。", file=sys.stderr)

    if args.print_tokens:
        print(json.dumps(theme["tokens"], ensure_ascii=False, indent=2))

    html_out, links = render(parse_markdown(text), theme, caption=not args.no_caption)

    if args.out:
        args.out.write_text(html_out, encoding="utf-8")
        print(f"已渲染：{args.out}（主题 {theme['id']}，{len(html_out)} 字节）")
    else:
        print(html_out)

    if links:
        print("\n注意：正文含外链，公众号正文外链通常不可点击，需单独处理：",
              file=sys.stderr)
        for url in links:
            print(f"  {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
