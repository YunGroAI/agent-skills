#!/usr/bin/env python3
"""YunGroAI 技能整仓同步：更新已安装技能，并安装仓库新增的技能。

对比 GitHub main 上 skills/*/SKILL.md 的 metadata.version 与本机已安装版本：
- 已安装且远端更新 → npx skills update <names>
- 仓库新增、本机未安装 → npx skills add YunGroAI/agent-skills --skill <names>
只输出一行 JSON，退出码恒为 0，任何失败都不应阻塞任务。

status：synced / up_to_date / update_available / manual / skipped / check_failed / sync_failed

用法：
  python3 scripts/sync.py                        # 检查并同步（24 小时内只查一次）
  python3 scripts/sync.py --agent claude-code    # 指定新技能安装到哪个 Agent（可重复）
  python3 scripts/sync.py --check-only --force   # 只检查不同步，忽略节流
环境变量：YUNGROAI_SKILLS_AUTO_UPDATE=0 关闭自动同步（仍会检查并提示）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "YunGroAI/agent-skills"
TREE_URL = "https://api.github.com/repos/" + REPO + "/git/trees/main?recursive=1"
RAW_URL = "https://raw.githubusercontent.com/" + REPO + "/main/skills/{name}/SKILL.md"
SKILL_PATH_RE = re.compile(r"^skills/([a-z0-9-]+)/SKILL\.md$")
FETCH_TIMEOUT = 5
SYNC_TIMEOUT = 300
THROTTLE_SECONDS = 24 * 3600
THROTTLE_KEY = "__repo__"

SCRIPT_PATH = Path(__file__).absolute()
SKILL_DIR = SCRIPT_PATH.parent.parent
MANAGER = SKILL_DIR.name
VERSION_RE = re.compile(r"^\s+version:\s*['\"]?(\d+\.\d+\.\d+)['\"]?\s*$", re.M)
INTERNAL_RE = re.compile(r"^\s+internal:\s*true\s*$", re.M)


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    return parts[1] if text.startswith("---") and len(parts) == 3 else ""


def version_of(text: str) -> str | None:
    match = VERSION_RE.search(frontmatter(text))
    return match.group(1) if match else None


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_file() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "yungroai-skills" / "sync.json"


def throttled() -> bool:
    last = read_json(cache_file()).get(THROTTLE_KEY, 0)
    return isinstance(last, (int, float)) and time.time() - last < THROTTLE_SECONDS


def mark_checked() -> None:
    path = cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**read_json(path), THROTTLE_KEY: int(time.time())}), encoding="utf-8")
    except OSError:
        pass


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "yungroai-skills"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def remote_skills() -> dict[str, str]:
    """返回远端可安装技能 {name: version}（跳过 internal 技能和缺版本号的技能）。"""
    tree = json.loads(fetch(TREE_URL)).get("tree", [])
    names = [m.group(1) for item in tree if (m := SKILL_PATH_RE.match(str(item.get("path", ""))))]
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda n: fetch(RAW_URL.format(name=n)), names))
    result = {}
    for name, text in zip(names, texts):
        version = version_of(text)
        if version and not INTERNAL_RE.search(frontmatter(text)):
            result[name] = version
    return result


def global_lock() -> Path:
    state = os.environ.get("XDG_STATE_HOME")
    return Path(state) / "skills" / ".skill-lock.json" if state else Path.home() / ".agents" / ".skill-lock.json"


def find_scope() -> tuple[str, Path, dict] | None:
    """找到记录本技能的 lock 文件：先项目级 skills-lock.json（向上查找），再全局。"""
    for start in (SCRIPT_PATH.parent, SKILL_DIR.resolve(), Path.cwd()):
        for directory in (start, *start.parents):
            data = read_json(directory / "skills-lock.json")
            if MANAGER in data.get("skills", {}):
                return "project", directory / "skills-lock.json", data
    data = read_json(global_lock())
    if MANAGER in data.get("skills", {}):
        return "global", global_lock(), data
    return None


def from_repo(entry: dict) -> bool:
    text = (str(entry.get("source", "")) + " " + str(entry.get("sourceUrl", ""))).lower()
    return entry.get("sourceType") == "github" and REPO.lower() in text


def local_version(name: str) -> str | None:
    """已安装技能与本技能位于同一个 skills 目录下。"""
    for base in (SKILL_DIR.parent, SKILL_DIR.resolve().parent):
        try:
            return version_of((base / name / "SKILL.md").read_text(encoding="utf-8"))
        except OSError:
            continue
    return None


def run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    npx = shutil.which("npx")
    if not npx:
        return False, "未找到 npx，需要先安装 Node.js"
    env = {**os.environ, "DISABLE_TELEMETRY": "1"}
    try:
        proc = subprocess.run([npx, *cmd[1:]], cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=SYNC_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return proc.returncode == 0, "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-5:])


def plan(remote: dict[str, str], installed: list[str]) -> tuple[list[dict], list[str], list[str]]:
    updates = []
    for name in installed:
        current, latest = local_version(name), remote.get(name)
        if current and latest and as_tuple(latest) > as_tuple(current):
            updates.append({"name": name, "from": current, "to": latest})
    new = sorted(set(remote) - set(installed))
    removed = sorted(set(installed) - set(remote))
    return updates, new, removed


def sync(args: argparse.Namespace) -> dict:
    if not args.force and throttled():
        return {"status": "skipped"}
    try:
        remote = remote_skills()
    except Exception as exc:  # 网络不可达、限流、超时等一律静默
        return {"status": "check_failed", "reason": type(exc).__name__}
    mark_checked()

    scope_info = find_scope()
    if not scope_info or not from_repo(scope_info[2]["skills"][MANAGER]):
        siblings = [n for n in remote if local_version(n)]
        updates, new, _ = plan(remote, siblings)
        if not updates and not new:
            return {"status": "up_to_date"}
        return {"status": "manual", "updates": updates, "new_skills": new,
                "hint": "当前安装方式不支持自动同步：执行 npx skills add " + REPO + " --skill '*' 安装全部技能，"
                        "或在本地仓库 git pull 后重新安装"}

    scope, lock, data = scope_info
    installed = [n for n, e in data.get("skills", {}).items() if isinstance(e, dict) and from_repo(e)]
    updates, new, removed = plan(remote, installed)
    scope_flag = ["-g"] if scope == "global" else []
    agents = args.agent or read_json(global_lock()).get("lastSelectedAgents") or []
    commands = []
    if updates:
        commands.append(["npx", "-y", "skills", "update", *[u["name"] for u in updates],
                         "-g" if scope == "global" else "-p", "-y"])
    if new:
        commands.append(["npx", "-y", "skills", "add", REPO, "--skill", *new,
                         *(["-a", *agents] if agents else []), *scope_flag, "-y"])
    result = {"scope": scope, "updates": updates, "new_skills": new, "removed_upstream": removed}
    if not commands:
        return {**result, "status": "up_to_date"}
    shown = [" ".join(c) for c in commands]
    if args.check_only or os.environ.get("YUNGROAI_SKILLS_AUTO_UPDATE") == "0":
        return {**result, "status": "update_available", "commands": shown}
    # 不知道目标 Agent 时，已安装技能照常更新，只把新技能留给 Agent 补充 --agent 后安装
    runnable = commands if agents or not new else commands[:-1]
    if not runnable:
        return {**result, "status": "update_available", "commands": shown,
                "reason": "未知目标 Agent：请带 --agent <当前 Agent 的 skills CLI 名称> 重新运行"}

    cwd = lock.parent if scope == "project" else Path.home()
    for cmd in runnable:
        ok, output = run(cmd, cwd)
        if not ok:
            return {**result, "status": "sync_failed", "commands": shown, "detail": output}
    missing = [n for n in new if agents and not local_version(n)]
    stale = [u["name"] for u in updates if local_version(u["name"]) != u["to"]]
    if missing or stale:
        return {**result, "status": "sync_failed", "commands": shown,
                "detail": "同步后仍未就绪：" + ", ".join(missing + stale)}
    if new and not agents:
        return {**result, "status": "synced", "commands": shown[-1:],
                "reason": "新技能未安装：未知目标 Agent，请带 --agent <当前 Agent 的 skills CLI 名称> 重新运行"}
    return {**result, "status": "synced"}


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 YunGroAI 技能：更新已安装技能并安装新技能")
    ap.add_argument("--agent", action="append", help="新技能的目标 Agent（skills CLI 名称，可重复）")
    ap.add_argument("--check-only", action="store_true", help="只检查，不执行同步")
    ap.add_argument("--force", action="store_true", help="忽略 24 小时节流")
    args = ap.parse_args()
    try:
        result = sync(args)
    except Exception as exc:  # 兜底：脚本自身出错也不阻塞任务
        result = {"status": "check_failed", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
