## 自动更新

<!-- yungroai:auto-update v1 -->
任务开始时运行一次 `python3 scripts/check_update.py`（本技能目录下），与依赖连接检查并行，不等它返回再做其它只读准备。
脚本只输出一行 JSON，按 `status` 处理：

- `updated`：用一句话告诉用户“本技能已从 `from` 更新到 `to`”，**重新读取本 SKILL.md** 及本次要用的参考文件后再继续。
- `update_available` / `manual`：用一句话提示有新版本，并附上返回的 `command` 或 `hint`，然后继续当前任务。
- `update_failed`：简述失败原因并附上 `command`，继续用当前版本完成任务。
- `up_to_date` / `skipped` / `check_failed`：不打扰用户，直接继续。

检查或更新失败都不阻塞任务；同一次任务只检查一次。用户设置 `YUNGROAI_SKILLS_AUTO_UPDATE=0` 时只提示、不自动更新。
