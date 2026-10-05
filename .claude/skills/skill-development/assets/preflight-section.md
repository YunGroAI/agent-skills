## 前置检查

<!-- yungroai:preflight v2 -->
本技能依赖 `YunGroAI` MCP 连接。任务开始时**先使用 `yungroai-skills` 技能**完成前置检查
（MCP 连接检查与引导安装、YunGroAI 技能同步），通过后再继续本技能。

- 未安装 `yungroai-skills` 时，告诉用户需要先安装它，征得同意后代为执行（或请用户执行）：
  `npx skills add YunGroAI/agent-skills --skill yungroai-skills`，装好后按它的指引完成检查。
- `YunGroAI` 连接不可用期间不调用任何 `YunGroAI` 工具，可以先做不依赖它的本地工作。
