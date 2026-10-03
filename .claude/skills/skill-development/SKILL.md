---
name: skill-development
description: 在 YunGroAI/agent-skills 仓库中新建、修改或发布技能时使用。按统一开发标准完成目录与 frontmatter、MCP 依赖内联、自动更新段落与脚本、版本递增和提交前自检，保证通过 CI（skills-standard）。
metadata:
  internal: true
---

# skill-development（本仓库技能开发流程）

规范以仓库根目录 `CLAUDE.md` 的「Skill development standard」为准；本技能只给出操作步骤。
`metadata.internal: true` 让 skills CLI 不会列出或安装本技能，不要删除这个标记。

## 新建技能

1. 建目录 `skills/<name>/`，`<name>` 为小写 kebab-case，最长 64 个字符，不与已有技能重名。
2. 写 `SKILL.md` frontmatter：

   ```yaml
   ---
   name: <name>
   description: <做什么 + 何时触发 + 不处理什么>
   metadata:
     version: 1.0.0
   ---
   ```

3. 把 [assets/mcp-dependency-section.md](assets/mcp-dependency-section.md) 和 [assets/auto-update-section.md](assets/auto-update-section.md) **按顺序原样**粘贴到「开始时」之前，不要修改其中任何文字。
   「开始时」第 1 步写成：按「依赖的 MCP 连接」一节检查 `YunGroAI`，未安装时主动引导安装；连接可用前不调用该技能的 MCP 工具。
4. 技能特有的 MCP 工具调用顺序写在「开始时」第 2 步及之后，不要改动模板段落。
5. 复制脚本：`cp .claude/skills/skill-development/assets/check_update.py skills/<name>/scripts/check_update.py`（不要修改副本）。
6. 较长的流程放在 `references/*.md`，并在 SKILL.md 中按场景链接。
7. 在 `README.md` 的技能表中加一行；如果连接器打包内容有变化，递增 `connector-meta.json` 的 `version`。

## 修改已有技能

- `skills/<name>/` 下有任何改动，都要递增该技能的 `metadata.version`：措辞或修复递增 patch，新增能力递增 minor，流程不兼容的变更递增 major。不递增版本，用户就收不到自动更新，CI 也会失败。
- 修改检查脚本、自动更新段落或 MCP 依赖段落时，先改 `assets/` 中的模板，再同步到**所有**技能，同时递增**所有**技能的版本。
- 修改 MCP 连接配置时，`mcp.json`、`README.md`、`assets/mcp-dependency-section.md` 和所有 `SKILL.md` 要一起改。

## 提交前自检

1. 运行 CI 同款检查：`act pull_request -W .github/workflows/skills-standard.yml`；没有安装 `act` 时，按 CLAUDE.md 的 CI 标注项逐条人工核对。
2. 在技能目录执行 `python3 scripts/check_update.py --check-only --force`，应返回一行 JSON 且不报错。
3. 完成 CLAUDE.md 中「Manual review」两项无法自动化的检查，并在 PR 中写明受影响的技能、新版本号和实际执行过的检查。
