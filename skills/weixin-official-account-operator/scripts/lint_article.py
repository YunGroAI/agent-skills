#!/usr/bin/env python3
"""公众号成稿体检：检查手机阅读节奏、开场钩子、生硬表达、AI 句式、人味信号、广告法极限词和结构元素。

用法：
  python3 scripts/lint_article.py 正文.md
  python3 scripts/lint_article.py 正文.md --strict     # 存在 ERROR 时退出码 1
  python3 scripts/lint_article.py 正文.md --json        # 机器可读输出

只做体检不改稿：报告给出问题、位置和修改方向，改写由 Agent 完成。
判定阈值是经验值，可在文件顶部 THRESHOLDS 调整。
仅依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ 阈值（可调经验值）

THRESHOLDS = {
    "first_screen_chars": 120,      # 首屏字数：手机一屏大约能看到的正文
    "long_paragraph_chars": 120,    # 单段超过这个字数就算"墙"
    "long_sentence_chars": 45,      # 单句超过这个字数不好读
    "heading_gap_chars": 600,       # 超过这个字数没有小标题就提醒
    "min_avg_sentence_short": 34,   # 平均句长软上限
    "max_title_chars": 32,          # 公众号标题上限
    "max_article_chars": 5000,      # 超过此长度建议拆分或强化节奏
}

# 开场即劝退的套话（命中即 ERROR）
OPENING_CLICHE = [
    "随着", "在当今", "近年来", "众所周知", "综上所述", "众所周知的是",
    "随着社会", "随着时代", "在当下", "伴随着", "日益", "愈发", "不难看出",
    "什么是", "本文将介绍", "本文旨在", "前言", "背景介绍",
    "在这个", "你是否也曾", "你是否曾经", "你有没有想过",
]

# 公文腔 / AI 腔高频词（命中即提示，按出现次数分级）
STIFF_WORDS = [
    "赋能", "抓手", "闭环", "沉淀", "对齐", "拉齐", "颗粒度", "生态位", "护城河",
    "深度融合", "全方位", "多维度", "进一步", "持续深耕", "稳步推进", "积极探索",
    "有效提升", "显著改善", "高度重视", "大力推动", "落到实处", "走深走实",
    "综上所述", "值得注意的是", "由此可见", "不难发现", "众所周知",
    "具有重要意义", "发挥着重要作用", "保驾护航", "再上新台阶", "开启新篇章",
    "总而言之", "总的来说", "让我们一起", "不可或缺", "至关重要", "不言而喻", "毋庸置疑",
    "与此同时", "深入探讨", "全面解析", "一文读懂", "息息相关", "重中之重",
]

# AI 句式：单个出现无妨，成批出现就是"机器腔"（名称, 正则, 允许出现的次数上限）
AI_PATTERNS = [
    ("「不是…而是…」", r"不是[^。！？!?\n]{1,30}而是", 1),
    ("序号连接词（首先/其次/再次）", r"首先|其次|再次|最后，", 2),
    ("「不仅…更/还…」递进", r"不仅[^。！？!?\n]{1,30}(更|还|也|而且)", 1),
    ("连续反问（你是不是/你有没有/你是否）", r"你是不是|你有没有|你是否", 2),
    ("破折号", r"——", 3),
    ("升华套话（更是一种/值得我们/每个人都应该）", r"更是一种|值得我们|每个人都应该|这正是|意味着什么", 1),
]

# 总结式结尾（出现在最后 150 字即提示）
SUMMARY_ENDING = ["总之", "总而言之", "综上", "总的来说", "希望本文", "希望这篇", "希望以上",
                  "希望对你有", "让我们一起", "感谢阅读", "以上就是"]

# 广告法极限词与效果承诺（转化文必查；"第一步""最后"等正常用法已排除）
AD_EXTREME = [
    r"最佳", r"最强", r"最好用", r"最低价", r"最高级", r"全网最", r"史上最", r"顶级", r"国家级",
    r"世界级", r"100%", r"百分百", r"绝对有效", r"万能", r"首选", r"零风险", r"唯一",
    r"第一(?![步次天个章篇段句眼时件回轮周年批位条种类点部集期届名])",
]

# 人味信号：第一人称、原话、具体时间
FIRST_PERSON_RE = re.compile(r"我|我们")
QUOTE_SPEECH_RE = re.compile(r"[「“\"][^」”\"]{2,60}[」”\"]")
CONCRETE_TIME_RE = re.compile(
    r"\d+\s*点|凌晨|上午|中午|下午|傍晚|晚上|昨天|前天|上周|上个月|去年|那天|那晚|周[一二三四五六日末]|星期")

# 抽象形容词：可用但成堆出现说明不具体
ABSTRACT_WORDS = ["重要", "关键", "核心", "高效", "优质", "全面", "专业", "领先", "创新", "系统性地"]

SENTENCE_SPLIT = re.compile(r"[。！？!?；;…]+|\n+")
IMAGE_RE = re.compile(r"^!\[")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
FENCE_RE = re.compile(r"^:::(card|cta|stat|note)")
QUOTE_RE = re.compile(r"^>")


# ------------------------------------------------------------------ 解析

def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = None
    headings: list[tuple[int, int, str]] = []      # (行号, 级别, 文本)
    paragraphs: list[tuple[int, str]] = []         # (行号, 文本)
    images = 0
    quotes = 0
    cards = 0
    stats = 0
    ctas = 0
    notes = 0

    buf: list[str] = []
    buf_start = 0

    def flush() -> None:
        nonlocal buf
        # 用换行而非空格拼接：列表项各自成句，避免被误判为超长句
        joined = "\n".join(x.strip() for x in buf if x.strip())
        if joined:
            paragraphs.append((buf_start, joined))
        buf = []

    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()

        heading = HEADING_RE.match(stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            body = heading.group(2).strip()
            headings.append((idx, level, body))
            if level == 1 and title is None:
                title = body
            continue
        if FENCE_RE.match(stripped):
            flush()
            kind = FENCE_RE.match(stripped).group(1)
            if kind == "card":
                cards += 1
            elif kind == "stat":
                stats += 1
            elif kind == "cta":
                ctas += 1
            else:
                notes += 1
            continue
        if IMAGE_RE.match(stripped):
            flush()
            images += 1
            continue
        if QUOTE_RE.match(stripped):
            flush()
            quotes += 1
            continue
        if stripped in ("---", "***", "___"):
            flush()
            continue
        if not stripped:
            flush()
            continue
        if not buf:
            buf_start = idx
        buf.append(stripped)
    flush()

    return {
        "text": text,
        "title": title,
        "headings": headings,
        "paragraphs": paragraphs,
        "images": images,
        "quotes": quotes,
        "cards": cards,
        "stats": stats,
        "ctas": ctas,
        "notes": notes,
    }


def body_text(doc: dict) -> str:
    """正文纯文本，用于首屏与结尾判断（跳过一级标题）。"""
    parts = []
    for _, level, body in doc["headings"]:
        if level > 1:
            parts.append(body)
    parts.extend(p for _, p in doc["paragraphs"])
    return "\n".join(parts)


def char_count(text: str) -> int:
    """中文按字计，英文按词计。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return cjk + words


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s and s.strip()]


# ------------------------------------------------------------------ 检查

def check(doc: dict) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    body = body_text(doc)
    total = char_count(body)
    sents = sentences(body)
    avg_sentence = round(sum(char_count(s) for s in sents) / len(sents), 1) if sents else 0.0

    metrics = {
        "字数": total,
        "段落数": len(doc["paragraphs"]),
        "句子数": len(sents),
        "平均句长": avg_sentence,
        "小标题数": len([h for h in doc["headings"] if h[1] > 1]),
        "配图数": doc["images"],
        "引语块": doc["quotes"],
        "结论卡": doc["cards"],
        "数字块": doc["stats"],
        "CTA": doc["ctas"],
        "预计手机屏数": max(1, round(total / 90) + doc["images"] * 3),
    }

    def add(level: str, item: str, detail: str, fix: str) -> None:
        issues.append({"level": level, "item": item, "detail": detail, "fix": fix})

    # 1. 标题
    if doc["title"]:
        t = doc["title"]
        if char_count(t) > THRESHOLDS["max_title_chars"]:
            add("ERROR", "标题过长", f"「{t}」{char_count(t)} 字",
                f"压到 {THRESHOLDS['max_title_chars']} 字内（公众号上限 32 字）")
        if not re.search(r"[\d你我？?！!：:]|如何|为什么|怎样|别|最|这|没想到|才发现|竟然|居然", t):
            add("WARN", "标题缺少抓手", f"「{t}」", "加上具体数字、第二人称或冲突/疑问，别用名词短语当标题")
    else:
        add("INFO", "无标题", "正文未含一级标题", "公众号标题另行确认，正文里通常不保留标题")

    # 2. 首屏钩子
    head = body[: THRESHOLDS["first_screen_chars"]]
    head_plain = re.sub(r"[#>*`\-]", "", head)
    hits = [w for w in OPENING_CLICHE if head_plain.startswith(w) or f"，{w}" in head_plain[:60]
            or head_plain[:40].count(w) > 0]
    if hits:
        add("ERROR", "开场套话", f"首屏命中：{'、'.join(sorted(set(hits)))}",
            "换成具体场景、一句冲突、一个数字或一句结论开头，删掉铺垫")
    if "你" not in head_plain and "我" not in head_plain:
        add("INFO", "首屏没有人", "前 120 字既没有「你」也没有「我」",
            "首屏要么让读者对号入座，要么让作者带着一个具体场景出场")
    if not re.search(r"\d", head_plain):
        add("INFO", "首屏无数字", "前 120 字没有具体数字", "放一个可感知的数字能显著提高停留（有真实数据时再加）")

    # 3. 段落节奏
    walls = [(ln, p) for ln, p in doc["paragraphs"]
             if char_count(p) > THRESHOLDS["long_paragraph_chars"]]
    if walls:
        add("ERROR", "存在文字墙",
            f"{len(walls)} 段超过 {THRESHOLDS['long_paragraph_chars']} 字，"
            f"最长 {max(char_count(p) for _, p in walls)} 字（首处在第 {walls[0][0]} 行）",
            "拆成 2–3 段，或抽成小标题 + 列表；手机单段控制在 3–4 行")

    # 4. 句长
    long_sents = [s for s in sents if char_count(s) > THRESHOLDS["long_sentence_chars"]]
    if long_sents:
        add("WARN", "超长句", f"{len(long_sents)} 句超过 {THRESHOLDS['long_sentence_chars']} 字",
            "拆短或改成「短句 + 短句」的节奏，长句留一句做强调即可")
    if avg_sentence > THRESHOLDS["min_avg_sentence_short"]:
        add("WARN", "平均句长偏长", f"平均 {avg_sentence} 字",
            "掺入口语短句（10–20 字）打断节奏，别全篇书面长句")

    # 5. 小标题密度
    h2 = [h for h in doc["headings"] if h[1] == 2]
    if len(doc["paragraphs"]) >= 4 and not h2:
        add("ERROR", "全文无小标题", f"{len(doc['paragraphs'])} 段正文没有二级标题",
            "每 300–500 字加一个「一句观点」式小标题，别用名词短语")
    else:
        for i, (ln, _, text) in enumerate(h2):
            if char_count(text) > 24:
                add("WARN", "小标题过长", f"第 {ln} 行：{text}",
                    "小标题压到 20 字内，写成一句带观点的短句")
            if re.search(r"[，。；]$", text) or "、" in text:
                add("INFO", "小标题像词组", f"第 {ln} 行：{text}", "改成有判断的短句，避免两个名词并列")

    # 6. 连续无小标题的字数
    if h2:
        spans = _heading_spans(doc)
        worst = max(spans, default=(0, 0))
        if worst[1] > THRESHOLDS["heading_gap_chars"]:
            add("WARN", "小标题间隔过大",
                f"最长 {worst[1]} 字没有二级标题（第 {worst[0]} 行附近）",
                f"控制在 {THRESHOLDS['heading_gap_chars']} 字以内，中间插小标题、引语或配图")

    # 7. 生硬表达
    stiff_hits = _word_hits(body, STIFF_WORDS)
    if stiff_hits:
        top = "、".join(f"{w}×{c}" for w, c in stiff_hits[:8])
        add("ERROR" if sum(c for _, c in stiff_hits) >= 5 else "WARN",
            "公文腔/AI 腔", f"{sum(c for _, c in stiff_hits)} 处：{top}",
            "换成具体的人、事、数字；能删就删，不靠形容词撑场面")
    abstract_hits = _word_hits(body, ABSTRACT_WORDS)
    if sum(c for _, c in abstract_hits) >= 8:
        add("WARN", "抽象词偏多", "、".join(f"{w}×{c}" for w, c in abstract_hits[:6]),
            "每个抽象判断后面补一个具体例子或数字，否则删掉这个判断")

    # 8. AI 句式
    ai_hits = []
    for name, pattern, allowed in AI_PATTERNS:
        c = len(re.findall(pattern, body))
        if c > allowed:
            ai_hits.append((name, c))
    if ai_hits:
        add("ERROR" if len(ai_hits) >= 3 else "WARN", "AI 句式",
            "、".join(f"{n}×{c}" for n, c in ai_hits),
            "按 references/voice.md 的 AI 味清单逐条改：删序号词、拆排比、少用「不是…而是…」，直接说结论")

    tail = body[-150:]
    endings = [w for w in SUMMARY_ENDING if w in tail]
    if endings:
        add("WARN", "总结式结尾", f"结尾出现：{'、'.join(endings)}",
            "删掉总结段，回到开头的场景，或给一个读者能回答的问题/立刻可做的一步")

    # 9. 人味信号
    signals = {
        "第一人称": bool(FIRST_PERSON_RE.search(body)),
        "原话/对话": bool(QUOTE_SPEECH_RE.search(doc["text"])),
        "具体时间": bool(CONCRETE_TIME_RE.search(body)),
    }
    metrics["人味信号"] = "、".join(k for k, v in signals.items() if v) or "无"
    if total > 600 and sum(signals.values()) == 0:
        add("WARN", "缺少人味信号", "全文没有第一人称、原话或具体时间",
            "补一个真实场景：谁、在什么时候、说了什么（见 references/voice.md 素材采访）")

    lens = [char_count(p) for _, p in doc["paragraphs"]]
    if len(lens) >= 6:
        mean = sum(lens) / len(lens)
        cv = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5 / mean if mean else 0
        if cv < 0.25:
            add("INFO", "段落长度过于均匀", f"{len(lens)} 段长度几乎一样（变异系数 {cv:.2f}）",
                "长短段交错，允许一句话成段制造停顿")

    # 10. 广告法极限词
    ad_hits = []
    for pattern in AD_EXTREME:
        found = re.findall(pattern, body)
        if found:
            ad_hits.append((re.sub(r"\(.*", "", pattern), len(found)))
    if ad_hits:
        add("WARN", "极限词/效果承诺", "、".join(f"{w}×{c}" for w, c in ad_hits),
            "广告法风险词：换成可验证的事实描述；确属正常用法（如引用原话）可保留并说明")

    # 11. 结构元素
    tail = body[-200:]
    if not re.search(r"[？?]", tail):
        add("INFO", "结尾没有问句", "最后 200 字没有问句",
            "结尾可以抛一个读者能回答的问题、给一个立刻可做的一步，或回到开头场景；不要写「感谢阅读」")
    if doc["cards"] == 0 and total > 800:
        add("INFO", "缺结论卡", "全文没有 :::card", "把最该被记住的一句话做成结论卡，方便截图传播")
    if doc["ctas"] == 0:
        add("INFO", "缺 CTA", "全文没有 :::cta", "按本篇目标补一个行动号召（关注/回复关键词/阅读原文）")
    if doc["images"] == 0 and total > 600:
        add("WARN", "无配图", f"{total} 字没有一张图",
            "按配图脚本补 2–4 张，或明确说明本篇不配图")
    if total > THRESHOLDS["max_article_chars"]:
        add("INFO", "篇幅偏长", f"{total} 字，约 {metrics['预计手机屏数']} 屏",
            "确认读者会读完；必要时拆成上下篇或加强小标题与配图密度")

    return issues, metrics


def _word_hits(text: str, words: list[str]) -> list[tuple[str, int]]:
    hits = []
    for w in words:
        c = text.count(w)
        if c:
            hits.append((w, c))
    hits.sort(key=lambda x: -x[1])
    return hits


def _heading_spans(doc: dict) -> list[tuple[int, int]]:
    """相邻二级标题之间的正文字数与起始行号。"""
    marks = [(ln, "h") for ln, level, _ in doc["headings"] if level == 2]
    marks += [(ln, "p") for ln, p in doc["paragraphs"] if char_count(p) > 0]
    marks.sort()
    spans: list[tuple[int, int]] = []
    start = None
    acc = 0
    for ln, kind in marks:
        if kind == "h":
            if start is not None:
                spans.append((start, acc))
            start, acc = ln, 0
        else:
            if start is None:
                start = ln
            acc += char_count(next(p for l2, p in doc["paragraphs"] if l2 == ln))
    if start is not None:
        spans.append((start, acc))
    return spans


# ------------------------------------------------------------------ 输出

def render(path: Path, issues: list[dict], metrics: dict) -> str:
    errors = [i for i in issues if i["level"] == "ERROR"]
    warns = [i for i in issues if i["level"] == "WARN"]
    infos = [i for i in issues if i["level"] == "INFO"]

    out = [f"# 成稿体检：{path.name}", ""]
    out.append("## 指标")
    out.append("")
    out.append("| 项 | 值 |")
    out.append("|---|---|")
    for k, v in metrics.items():
        out.append(f"| {k} | {v} |")
    out.append("")
    out.append(f"结论：ERROR {len(errors)} / WARN {len(warns)} / INFO {len(infos)}")
    out.append("")
    for level, group in (("ERROR", errors), ("WARN", warns), ("INFO", infos)):
        if not group:
            continue
        out.append(f"## {level}")
        out.append("")
        for i in group:
            out.append(f"- **{i['item']}**：{i['detail']}")
            out.append(f"  - 怎么改：{i['fix']}")
        out.append("")
    if not issues:
        out.append("未发现明显问题。仍建议朗读一遍，拗口处就地改短。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号成稿体检（只读，不改稿）")
    ap.add_argument("article", type=Path, help="Markdown 正文文件")
    ap.add_argument("--strict", action="store_true", help="存在 ERROR 时退出码 1")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if not args.article.is_file():
        print(f"文件不存在：{args.article}", file=sys.stderr)
        return 2

    doc = parse(args.article)
    issues, metrics = check(doc)

    if args.json:
        print(json.dumps({"metrics": metrics, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        print(render(args.article, issues, metrics))

    if args.strict and any(i["level"] == "ERROR" for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
