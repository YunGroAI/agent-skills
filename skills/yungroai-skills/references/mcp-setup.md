# 在常见 Agent 中添加 YunGroAI 连接

配置项都一样：服务器名 `YunGroAI`，传输类型 Streamable HTTP，地址 `https://agent.uboosts.com/mcp`，
不需要任何密钥或令牌。先检查有没有同名连接，有就不重复添加。
下表命令来自各 Agent 的官方 CLI；版本不同导致命令报错时，按该 Agent 当前文档调整，不改服务器名和地址。

| Agent | 检查 | 添加 | 授权 |
|---|---|---|---|
| Claude Code（终端或桌面应用的 Code） | `claude mcp get YunGroAI` | `claude mcp add --transport http --scope user YunGroAI https://agent.uboosts.com/mcp` | 新会话中运行 `/mcp`，选中 `YunGroAI` 完成浏览器授权；会话里有该连接的授权工具时直接调用 |
| Codex | `codex mcp get YunGroAI` | `codex mcp add YunGroAI --url https://agent.uboosts.com/mcp` | `codex mcp login YunGroAI`（自动打开浏览器） |
| Cursor | 设置中的 MCP 列表 | 在用户级 `mcp.json` 的 `mcpServers` 中加入 `"YunGroAI": { "url": "https://agent.uboosts.com/mcp" }` | 设置的 MCP 列表中点击 `YunGroAI` 的登录 |
| Claude 桌面应用 / 网页版的对话 | 设置 → 连接器 | 只能由用户在界面操作：设置 → 连接器 → 添加自定义连接器，名称 `YunGroAI`，填入地址 | 添加后点击连接，在浏览器中登录并同意 |

说明：

- Claude Code 用 `--scope user`，连接在所有项目中都可用，也不会写进项目配置被提交到代码仓库。
- 添加后，多数 Agent 要在**新会话**里才会加载新连接：把「开新会话」和授权入口一次告诉用户，
  新会话中再用 `yungroai-skills` 检查一遍。
- 找不到上表的命令行（例如命令不在 PATH 中）时，不要直接改写 Agent 的内部配置文件，
  改为给出该 Agent 界面中的添加步骤。
