#!/usr/bin/env python3
"""技能自动更新检查（YunGroAI/agent-skills 所有技能共用，各技能内副本必须与模板一致）。

对比本技能 SKILL.md 的 metadata.version 与 GitHub main 分支上的版本；
若通过 `npx skills add YunGroAI/agent-skills` 安装且有新版本，调用 `npx skills update` 自动更新。
只输出一行 JSON，退出码恒为 0，任何失败都不应阻塞任务。

status：updated / update_available / manual / up_to_date / skipped / check_failed / update_failed

用法：
  python3 scripts/check_update.py                 # 检查并按需自动更新（24 小时内只查一次）
  python3 scripts/check_update.py --check-only    # 只检查不更新
  python3 scripts/check_update.py --force         # 忽略 24 小时节流
环境变量：YUNGROAI_SKILLS_AUTO_UPDATE=0 关闭自动更新（仍会检查并提示）。
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
from pathlib import Path

REPO = "YunGroAI/agent-skills"
RAW_URL = "https://raw.githubusercontent.com/" + REPO + "/main/skills/{name}/SKILL.md"
FETCH_TIMEOUT = 3
UPDATE_TIMEOUT = 120
THROTTLE_SECONDS = 24 * 3600

SKILL_DIR = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^\s+version:\s*['\"]?(\d+\.\d+\.\d+)['\"]?\s*$", re.M)
NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.M)


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    return parts[1] if text.startswith("---") and len(parts) == 3 else ""


def parse_meta(text: str) -> tuple[str | None, str | None]:
    fm = frontmatter(text)
    name = NAME_RE.search(fm)
    version = VERSION_RE.search(fm)
    return (name.group(1) if name else None, version.group(1) if version else None)


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def cache_file() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "yungroai-skills" / "update-check.json"


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def throttled(name: str) -> bool:
    last = read_json(cache_file()).get(name, 0)
    return isinstance(last, (int, float)) and time.time() - last < THROTTLE_SECONDS


def mark_checked(name: str) -> None:
    path = cache_file()
    data = {**read_json(path), name: int(time.time())}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def fetch_remote_version(name: str) -> str | None:
    req = urllib.request.Request(RAW_URL.format(name=name), headers={"User-Agent": "yungroai-skill-update"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return parse_meta(resp.read().decode("utf-8"))[1]


def lock_candidates() -> list[tuple[str, Path]]:
    """项目级 skills-lock.json（从技能目录和当前目录向上查找）与全局 .skill-lock.json。"""
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for start in (Path(__file__).absolute().parent, SKILL_DIR, Path.cwd()):
        for directory in (start, *start.parents):
            lock = directory / "skills-lock.json"
            if lock.is_file() and lock not in seen:
                seen.add(lock)
                found.append(("project", lock))
                break
    state = os.environ.get("XDG_STATE_HOME")
    global_lock = Path(state) / "skills" / ".skill-lock.json" if state else Path.home() / ".agents" / ".skill-lock.json"
    if global_lock.is_file():
        found.append(("global", global_lock))
    return found


def find_install(name: str) -> tuple[str, Path, dict] | None:
    for scope, lock in lock_candidates():
        entry = read_json(lock).get("skills", {}).get(name)
        if isinstance(entry, dict):
            return scope, lock, entry
    return None


def from_this_repo(entry: dict) -> bool:
    text = (str(entry.get("source", "")) + " " + str(entry.get("sourceUrl", ""))).lower()
    return REPO.lower() in text


def update_command(name: str, scope: str) -> list[str]:
    return ["npx", "-y", "skills", "update", name, "-g" if scope == "global" else "-p", "-y"]


def run_update(name: str, scope: str, lock: Path) -> tuple[bool, str]:
    npx = shutil.which("npx")
    if not npx:
        return False, "未找到 npx，需要先安装 Node.js"
    cmd = [npx, *update_command(name, scope)[1:]]
    cwd = lock.parent if scope == "project" else Path.home()
    env = {**os.environ, "DISABLE_TELEMETRY": "1"}
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=UPDATE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-5:])
    return proc.returncode == 0, tail


def check(args: argparse.Namespace) -> dict:
    name, local = parse_meta((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    if not name or not local:
        return {"status": "check_failed", "reason": "SKILL.md 缺少 name 或 metadata.version"}
    result = {"skill": name, "current": local}
    if not args.force and throttled(name):
        return {**result, "status": "skipped"}
    try:
        latest = fetch_remote_version(name)
    except Exception as exc:  # 网络不可达、DNS、超时等一律静默
        return {**result, "status": "check_failed", "reason": type(exc).__name__}
    mark_checked(name)
    if not latest or as_tuple(latest) <= as_tuple(local):
        return {**result, "status": "up_to_date", "latest": latest}
    result = {**result, "latest": latest}

    install = find_install(name)
    if not install or not from_this_repo(install[2]) or install[2].get("sourceType") != "github":
        local_path = install and install[2].get("sourceType") == "local"
        hint = (
            "本地路径安装：在本地仓库执行 git pull 后重新运行 npx skills add <仓库路径> --skill " + name
            if local_path
            else "当前安装方式不支持自动更新：可改用 npx skills add " + REPO + " --skill " + name
            + " 安装，或通过原安装渠道更新"
        )
        return {**result, "status": "manual", "hint": hint}

    scope, lock, _ = install
    command = " ".join(update_command(name, scope))
    if args.check_only or os.environ.get("YUNGROAI_SKILLS_AUTO_UPDATE") == "0":
        return {**result, "status": "update_available", "command": command}

    ok, output = run_update(name, scope, lock)
    after = parse_meta((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))[1]
    if ok and after and as_tuple(after) >= as_tuple(latest):
        return {**result, "status": "updated", "from": local, "to": after}
    return {**result, "status": "update_failed", "command": command, "detail": output}


def main() -> int:
    ap = argparse.ArgumentParser(description="检查并自动更新本技能")
    ap.add_argument("--check-only", action="store_true", help="只检查，不执行更新")
    ap.add_argument("--force", action="store_true", help="忽略 24 小时节流")
    args = ap.parse_args()
    try:
        result = check(args)
    except Exception as exc:  # 兜底：检查脚本本身出错也不阻塞任务
        result = {"status": "check_failed", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
