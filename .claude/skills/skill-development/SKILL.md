---
name: skill-development
description: 在 YunGroAI/agent-skills 仓库中新建、修改或发布技能时使用。按统一开发标准完成目录与 frontmatter、前置检查段落、版本递增和提交前自检，保证通过 CI（skills-standard）。
metadata:
  internal: true
---

# skill-development（本仓库技能开发流程）

规范以仓库根目录 `CLAUDE.md` 的「Skill development standard」为准；本技能只给出操作步骤。
`metadata.internal: true` 让 skills CLI 不会列出或安装本技能，不要删除这个标记。

## 职责划分

- `skills/yungroai-skills/`：**唯一**定义 MCP 依赖（检查、引导安装、完整配置）和技能同步（`scripts/sync.py`）的地方。
- 业务技能：只放业务流程，开头原样粘贴「前置检查」段落，把依赖与更新交给 `yungroai-skills`。
  不得出现 `mcpServers` 配置或任何更新脚本（CI 检查）。

## 新建业务技能

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

3. 把 [assets/preflight-section.md](assets/preflight-section.md) **原样**粘贴到「开始时」之前，不要修改其中任何文字。
   「开始时」第 1 步写成：先完成「前置检查」；`YunGroAI` 连接可用前不调用该技能的 MCP 工具。
4. 技能特有的 MCP 工具调用顺序写在「开始时」第 2 步及之后。
5. 较长的流程放在 `references/*.md`，并在 SKILL.md 中按场景链接。
6. 在 `README.md` 的技能表中加一行；递增 `connector-meta.json` 的 `version`。
   新技能推送到 main 后，已安装 `yungroai-skills` 的用户会在下次同步时自动装上它，不需要改 `yungroai-skills`。

## 修改已有技能

- `skills/<name>/` 下有任何改动，都要递增该技能的 `metadata.version`：措辞或修复递增 patch，新增能力递增 minor，流程不兼容的变更递增 major。不递增版本，用户就收不到更新，CI 也会失败。
- 修改「前置检查」段落时，先改 [assets/preflight-section.md](assets/preflight-section.md)，再同步到**所有**业务技能，并递增它们的版本。
- 修改 MCP 连接配置时，`mcp.json`、`README.md` 和 `skills/yungroai-skills/SKILL.md` 要一起改，并递增 `yungroai-skills` 的版本。

## 提交前自检

1. 运行 CI 同款检查：`act pull_request -W .github/workflows/skills-standard.yml`；没有安装 `act` 时，按 CLAUDE.md 的 CI 标注项逐条人工核对。
2. 修改了 `yungroai-skills` 时，在其目录执行 `python3 scripts/sync.py --check-only --force`，应返回一行 JSON 且不报错。
3. 完成 CLAUDE.md 中「Manual review」两项无法自动化的检查，并在 PR 中写明受影响的技能、新版本号和实际执行过的检查。
