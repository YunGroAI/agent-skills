# YunGroAI Agent Skills

本仓库维护依赖 **YunGroAI 增长引擎** MCP 的通用 Agent Skills。技能描述运营流程；MCP 提供工具、凭据和授权。当前提供公众号增长运营技能，覆盖主题锁定、热门文章对标与爆文逻辑改写、写作、主题风格排版与配图规划、草稿与发表、私信、粉丝运营和数据复盘。该技能内置 8 套主题风格模板，可按发表内容自动匹配或按品牌色派生定制，并提供成稿体检脚本（开场钩子、段落节奏、公文腔、结构元素）和一键流水线脚本 `build_article.py`（体检 → 主题推荐 → 渲染）。技能强调“本地迭代、一次落地”以提升运营效率：只读调用并行、路径预检按需、选题与提纲合并确认。技能在执行上还有两条硬约束：**多账号必须由用户点名**（每个 `weixin_oa_*` 调用显式带 `connection_id`，换号等于重来），以及**副作用闸门**——改稿在本地迭代，图床部署、图片上传、写草稿攒到用户最终确认后一次性执行，发表 / 预览 / 客服消息 / 菜单等对外动作逐条复述账号与对象后再操作。实际可用操作以 MCP 返回的账号能力为准。

## 安装

推荐使用 [Vercel Labs 的 skills CLI](https://github.com/vercel-labs/skills) 安装。需要 Node.js 和 `npx`。在目标项目目录中运行以下命令，从本地仓库安装公众号技能：

```bash
npx skills add /absolute/path/to/agent-skills --skill weixin-official-account-operator
```

仓库发布到 GitHub 后，可改用远程来源：

```bash
npx skills add uboosts/agent-skills --skill weixin-official-account-operator
```

安装前可用 `npx skills add /absolute/path/to/agent-skills --list` 查看可用技能。CLI 默认安装到当前项目；需要在所有项目中使用时，加 `-g` 全局安装。按 CLI 提示选择目标 Agent 和安装方式。

技能**自包含声明**它所依赖的 MCP，且**与客户端无关**：即使单独安装某个技能目录，也能从技能内部拿到完整连接配置；WorkBuddy、Claude Code / Claude Desktop、Codex 或任何支持 MCP 的客户端都能使用，使用客户端中名为 `YunGroAI` 的连接即可，也支持用户自行配置的同名本地调试服务，无需替换为远程地址。技能按名称识别依赖，不核对实际地址或证书；名称匹配不代表服务身份认证。未配置时，按技能内的默认远程配置引导安装；已配置但不可用时引导重连或排障，不要当成公众号账号无权限。默认远程配置如下：

```json
{
  "mcpServers": {
    "YunGroAI": {
      "type": "streamableHttp",
      "url": "https://agent.uboosts.com/mcp"
    }
  }
}
```

如客户端要求授权，按其提示完成；不要将微信密钥或固定令牌写入技能或配置示例。安装技能本身不会自动配置 MCP 连接。

## 连接器元数据

仓库根目录包含 [WorkBuddy 连接器市场](https://open.workbuddy.cn/docs/connector#mcp-skill-%E6%8E%A5%E5%85%A5)所需的元数据，采用 MCP + Skill 接入方式：

```text
.
├── connector-meta.json          # 连接器元信息（名称、描述、使用示例）
├── mcp.json                     # MCP Server 连接配置（streamableHttp）
├── icon.svg                     # 市场图标（云穹 AI 图形标）
└── skills/
    └── weixin-official-account-operator/
        └── SKILL.md
```

这些文件只用于 WorkBuddy 连接器市场分发，技能本身不依赖它们。

`source` 为 `yungroai`，`type` 为 `mcp`，远程地址使用 HTTPS streamableHttp；认证走标准 MCP 流程，不在任何配置中写入固定凭证。

`mcp.json` 是给连接器打包用的配置副本，技能并不在运行时读取它——技能可单独签发安装，配置必须写在技能内部。每个技能与 README 都要自带完整的 `mcpServers` 示例且与 `mcp.json` 保持一致，技能文案也不得引用仓库文件路径。改动连接配置时，`mcp.json`、README 与各技能内的示例要同时更新。

技能还必须保持**客户端无关与机器无关**：不得出现某个客户端专有的配置路径或操作入口（如 `~/.workbuddy/mcp.json`、连接器管理页、某客户端专属部署工具），也不得写死任何本机绝对路径。这些要求适用于 `skills/` 下的所有文件。

更新元数据时递增 `connector-meta.json` 的 `version`，按 [AGENTS.md](AGENTS.md) 中的规范完成检查后，将整个目录打包提交 WorkBuddy 团队审核。

## 编写规范

项目技能编写规范统一维护在 [AGENTS.md](AGENTS.md)，涵盖技能结构、命名、MCP 依赖声明、客户端无关性和连接器元数据。新增或修改技能时遵循该文件，并在提交前完成其中的人工检查；仓库不再提供自动校验脚本或对应 CI。
