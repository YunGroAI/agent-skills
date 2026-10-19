# 技能自动安装与更新

YunGroAI 技能只用 [skills CLI](https://github.com/vercel-labs/skills)（`npx skills`，需要 Node.js）安装和更新。
CLI 通过 git 拉取仓库，不受 GitHub API 限流影响。以下命令都在 shell 中执行；当前 Agent 不能执行命令时，
把命令告诉用户，请用户执行。

## 0. 前提判断

1. **关闭开关**：环境变量 `YUNGROAI_SKILLS_AUTO_UPDATE` 为 `0` 时，不自动安装或更新，只给出命令。
2. **安装来源与作用域**：执行 `npx skills list -g --json`（项目内安装去掉 `-g`），找到 `yungroai-skills` 这一项：
   - `scope` 决定后续命令用 `-g`（global）还是不带 `-g`（project）；
   - `source` 不是 `YunGroAI/agent-skills`（例如从本地目录安装的开发版，或客户端内置的技能）时，
     **不自动安装或更新**，只告诉用户对应命令，避免覆盖用户自己的安装方式；
   - 记下各已装技能的 `path`，交接时读取其中的 `SKILL.md`。

找不到 `npx` 或命令失败时，跳过自动安装与更新，告诉用户需要 Node.js，然后继续原任务能做的部分。

## 1. 每日更新

用一个时间戳文件节流，满 24 小时才更新一次：

```bash
f="${XDG_CACHE_HOME:-$HOME/.cache}/yungroai-skills/last-check"
now=$(date +%s); last=$(cat "$f" 2>/dev/null || echo 0)
[ $((now - last)) -ge 86400 ] && echo due || echo skip
```

- `skip`：不更新，继续任务。用户明确要求更新时忽略节流，直接执行下一步。
- `due`：执行更新，**无论成功与否**都写入新时间戳（避免离线时每次任务都卡在更新上）：

```bash
npx skills update -g -y
mkdir -p "$(dirname "$f")" && date +%s > "$f"
```

项目内安装把 `-g` 换成 `-p`。`update` 只更新有变化的技能。
更新后用一句话告诉用户哪些技能更新了；没有变化不用提。
如果本技能或当前要用的技能被更新，重新读取它的 `SKILL.md` 再继续，确保按最新流程执行。
不能读写时间戳文件的环境（例如没有 shell）：只在用户直接调用本技能或要求更新时更新。

## 2. 按需安装

匹配到的技能不在已装列表中时，只安装这一个，作用域与 `yungroai-skills` 相同：

```bash
npx skills add YunGroAI/agent-skills --skill <技能名> -g -y -a <当前 Agent 在 skills CLI 中的名称>
```

- `-a` 填当前 Agent 在 skills CLI 中的名称（如 `claude-code`、`codex`、`cursor`）；无法判断时问用户。
- 装好后用 `npx skills list -g --json` 拿到它的 `path`，**直接读取该目录的 `SKILL.md`** 接着执行原任务。
  新装的技能通常要在新会话里才会被 Agent 自动识别，告诉用户这一点，但不要让用户为此中断当前任务。
- 安装失败时说明原因（网络、权限、Node.js 缺失），给出上面的命令请用户执行；不要改用其它来源安装。

## 3. 目录兜底

「技能目录」里没有适合用户任务的技能时，查一次仓库的最新清单（可能有比本地目录更新的技能）：

```bash
npx skills add YunGroAI/agent-skills --list
```

清单里有合适的技能 → 按「按需安装」处理，并执行一次「每日更新」（忽略节流）让技能目录也更新到最新。
仍然没有 → 告诉用户 YunGroAI 暂无对应技能，不要硬套不相关的技能。
