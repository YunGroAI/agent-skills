# YunGroAI Agent Skills

本仓库维护依赖 **YunGroAI 增长引擎** MCP 的通用 Agent Skills。技能描述运营流程；MCP 提供工具、凭据和授权。

| 技能 | 用途 |
|---|---|
| `weixin-official-account-operator` | 公众号增长运营：主题锁定、热门文章对标与爆文逻辑改写、写作、排版与配图、草稿与发表、私信与粉丝运营、数据复盘 |

`weixin-official-account-operator` 要点：

- 内置 8 套主题风格模板，可按内容自动匹配或按品牌色派生；`build_article.py` 一条命令完成成稿体检 → 主题推荐 → 渲染。
- **本地迭代、一次落地**：改稿在本地进行，图床部署、图片上传、写草稿攒到用户最终确认后一次性执行。
- **多账号必须由用户点名**：每个 `weixin_oa_*` 调用显式带 `connection_id`，换号等于重来。
- 发表、预览、客服消息、菜单等对外动作逐条复述账号与对象后再操作；实际可用操作以 MCP 返回的账号能力为准。

## 安装

推荐使用 [Vercel Labs 的 skills CLI](https://github.com/vercel-labs/skills) 安装。需要 Node.js 和 `npx`。支持从公开 GitHub 仓库或本地目录安装，在目标项目目录中运行对应命令即可。

**从公开仓库安装**（推荐，仓库地址 [YunGroAI/agent-skills](https://github.com/YunGroAI/agent-skills)）：

```bash
npx skills add YunGroAI/agent-skills --skill weixin-official-account-operator
```

**从本地目录安装**（适合本地调试或离线使用，先克隆或下载本仓库）：

```bash
npx skills add /absolute/path/to/agent-skills --skill weixin-official-account-operator
```

安装前可用 `npx skills add YunGroAI/agent-skills --list`（或把来源换成本地路径）查看可用技能。CLI 默认安装到当前项目；需要在所有项目中使用时，加 `-g` 全局安装。按 CLI 提示选择目标 Agent 和安装方式。

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

`mcp.json` 是打包用的配置副本；改动连接配置时，`mcp.json`、README 与各技能内的示例要同时更新。更新元数据时递增 `connector-meta.json` 的 `version`，完成检查后将整个目录打包提交 WorkBuddy 团队审核。

## 编写规范

技能结构、命名、MCP 依赖声明、客户端与机器无关性、连接器元数据字段和提交前人工检查，统一维护在 [AGENTS.md](AGENTS.md)。仓库没有自动校验脚本或 CI。
