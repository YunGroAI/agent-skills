#!/usr/bin/env python3
"""公众号标题候选评分：按启发式规则给多个标题打分并列出加减分原因。

用法：
  python3 scripts/score_title.py "标题一" "标题二" "标题三"
  python3 scripts/score_title.py --json "标题一" "标题二"

分数只用于横向比较候选、发现明显毛病，不预测打开率；规则权重是可调经验值。
仅依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from lint_article import AD_EXTREME, STIFF_WORDS, char_count

BASE = 30

# 标题党词：短期可能拉点击，但伤信任，也是 AI 爆款腔的典型特征
CLICKBAIT = ["震惊", "必看", "速看", "疯传", "重磅", "刚刚", "紧急", "万万没想到", "99%的人",
             "吓人", "炸了", "封神", "绝绝子", "建议收藏", "看完沉默", "泪目"]

# 论文/报告式标题词
ACADEMIC = ["浅谈", "浅析", "探讨", "研究", "之我见", "概述", "综述", "的思考", "的启示"]

CONFLICT_RE = re.compile(r"[？?]|为什么|却|但|反而|没想到|才发现|别|不要|千万|居然|竟")
SCENE_RE = re.compile(r"\d+\s*点|凌晨|上午|下午|晚上|周[一二三四五六日末]|那天|那年|第\d+天|昨天|去年")


def score(title: str) -> dict:
    points = BASE
    reasons: list[str] = []

    def adj(delta: int, why: str) -> None:
        nonlocal points
        points += delta
        reasons.append(f"{'+' if delta > 0 else ''}{delta} {why}")

    n = char_count(title)
    if n > 32:
        adj(-30, f"{n} 字，超过公众号 32 字上限")
    elif 12 <= n <= 28:
        adj(15, f"{n} 字，手机两行内")
    elif n < 10:
        adj(-5, f"{n} 字，过短，信息不足")
    else:
        adj(5, f"{n} 字，长度可接受")

    if re.search(r"\d", title):
        adj(15, "有具体数字")
    if re.search(r"你|我", title):
        adj(10, "有人称，读者能对号入座")
    if CONFLICT_RE.search(title):
        adj(15, "有冲突、悬念或疑问")
    if SCENE_RE.search(title):
        adj(10, "有具体场景/时间")

    bait = [w for w in CLICKBAIT if w in title]
    if bait:
        adj(-20, f"标题党词：{'、'.join(bait)}（伤信任）")
    stiff = [w for w in STIFF_WORDS if w in title]
    if stiff:
        adj(-10, f"公文腔/AI 腔：{'、'.join(stiff)}")
    academic = [w for w in ACADEMIC if w in title]
    if academic:
        adj(-10, f"论文腔：{'、'.join(academic)}")
    ads = [m.group(0) for p in AD_EXTREME for m in [re.search(p, title)] if m]
    if ads:
        adj(-15, f"极限词：{'、'.join(ads)}（广告法风险）")
    if re.search(r"[！!]{2,}|[？?]{2,}", title):
        adj(-5, "标点堆叠")
    if not re.search(r"[你我他她它是有在把被让给要会能做用写说看想变成得了过]", title):
        adj(-5, "像名词短语，缺少动作")

    return {"title": title, "score": max(0, min(100, points)), "reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号标题候选评分（启发式，只读）")
    ap.add_argument("titles", nargs="+", help="一个或多个候选标题")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    results = sorted((score(t.strip()) for t in args.titles if t.strip()),
                     key=lambda r: -r["score"])
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    print("| 排名 | 分数 | 标题 | 加减分 |")
    print("|---|---|---|---|")
    for i, r in enumerate(results, start=1):
        print(f"| {i} | {r['score']} | {r['title']} | {'；'.join(r['reasons'])} |")
    print("\n分数是启发式参考，不预测打开率；同时检查标题承诺能否在正文兑现。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
