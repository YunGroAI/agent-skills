# 查询与恢复（错误码唯一真源）

服务端错误统一返回 `{code, message, retryable}`，部分带 `diagnostic`。
微信侧错误额外带 `wechat_errcode`，`40164`/`61004` 时还会带 `source_ip`。
**只有 `BUSY` 和 `RATE_LIMITED` 的 `retryable` 为 true，其余一律不要盲目重试。**
未在下表出现的 code：原样报出，不猜含义、不自行换工具绕过。

## 域内错误码

| code | retryable | 含义 | 处置 |
|---|---|---|---|
| ACCOUNT_SELECTION_REQUIRED | false | 需要指定有效公众号连接 | 从 `weixin_core_list_accounts` 取 `connection_id` 后重传，不猜测 |
| RESOURCE_NOT_FOUND | false | 连接不存在 | 只说明当前用户无法访问，不推测其他用户资源是否存在 |
| AUTHORIZATION_REVOKED | false | 连接已断开或微信授权已撤销 | 查 `weixin_core_get_authorization_status`，按用户需要重新授权 |
| NOT_CONFIGURED | false | 服务端未配置开放平台 | 扫码入口不可用，提示由部署管理员配置，不索要密钥 |
| TICKET_MISSING | false | 未收到微信 component_verify_ticket | 同上，属部署侧问题，等待回调或联系管理员 |
| INVALID_AUTHORIZATION | false | 授权会话已过期或已使用 | 重新发起 `weixin_core_start_authorization` |
| INSUFFICIENT_SCOPE | false | 公众号未授权该能力所需权限集 | 说明权限不足；再次授权可能仍受账号资质限制（见 48001） |
| CAPABILITY_UNVERIFIED | false | 该部署尚未验证此能力契约 | 明确能力未验收，不改开关、不换接口绕过 |
| IDEMPOTENCY_CONFLICT | false | 幂等键已用于不同参数 | 检查是否错误复用键，不自动换键重复动作 |
| CONTENT_CHANGED | false | 草稿已变化 | 重新 `weixin_oa_get_draft` 取最新 `draft_digest`，重新取得批准 |
| INVALID_DATE_RANGE | false | 日期不合法 | 区间有序、最多 7 天、早于北京时间今天；发表数据仅 2025-11-01 及之后 |
| INVALID_IMAGE_URL | false | 图片地址不合规 | 必须是无用户信息的 HTTPS 公网地址，换地址再传 |
| INVALID_IMAGE | false | 服务端取图失败或地址被判不安全 | 做第三方图对照测试判定故障层，见 publishing.md |
| MESSAGE_WINDOW_CLOSED | false | 无已验证的 48 小时用户消息窗口 | 不能发送客服消息；请用户重新发消息开启窗口，不换渠道触达 |
| BUSY | **true** | 资源正在处理中 | 用同一幂等键原样重放取已记录结果；仍未知就用读取工具（如 `weixin_oa_list_drafts`、`weixin_oa_get_publish_status`）核实，别换键重发；实测最终多为 failed |
| OPERATION_OUTCOME_UNKNOWN | false | 结果未知或仍在执行 | 用读取工具或微信后台核实实际状态，不换键重发 |
| RESULT_EXPIRED | false | 操作已执行但结果缓存过期 | 查询微信侧实际状态，不当成未执行 |
| RATE_LIMITED | **true** | 请求过于频繁 | 遵守提示等待（通常 1 分钟），不并发轰炸 |

## 微信错误码映射

| wechat_errcode | code | 处置 |
|---|---|---|
| 40001 / 40014 | TOKEN_INVALID | 服务会自动重新申请 token；确认账号仍有效后重试一次，持续失败转报障 |
| 42001 | TOKEN_EXPIRED | 同上，服务自动刷新；重试一次即可，不要反复轰炸 |
| 45009 | RATE_LIMITED | 等待后重试 |
| 48001 / 61007 | INSUFFICIENT_SCOPE | 见下方「资质限制」 |
| 40164 / 61004 | IP_NOT_WHITELISTED | 见下方「IP 白名单」 |
| -1 | WECHAT_BUSY | 稍后用同一幂等键重放或用读取工具核实，不换键重发 |
| 其它（40005、40113 等） | WECHAT_REJECTED | 报出原始 `wechat_errcode`；40005/40113 先做第三方图对照，详见 publishing.md |

### IP 白名单（40164 / 61004）

**第一步先看响应里有没有 `source_ip` 字段**（服务会从微信报错中解析出，如 `"source_ip": "45.138.210.212"`），
有就让用户把这个 IP 加进公众号后台「开发接口管理 → 基本配置 → IP 白名单」。
没有 `source_ip` 时，才让用户向服务方索取出口 IP 列表。
⚠️ **不要让用户在本机执行 `curl api.ipify.org` 去猜**——服务端出口 IP 通常与用户本机不是同一个。

**加白后可直接重试一次**：服务会重新申请并缓存 token，不需要重启服务。
加白之前的重试才是无效的，不要轰炸。若历史上加过白又复现，多半是服务端换了一批部署地址，重取一次 `source_ip`。

### 资质限制（48001 / 61007）

属于账号资质限制（常见于未认证订阅号/个人主体），重新授权也拿不到，重试无意义。
数据统计（datacube）、用户管理、freepublish 发表等同族接口会一起不可用。
替代路径：后台导出数据 / 后台手动群发。此时不要声称「文章列表为空＝没发过文章」。
**草稿可写不代表能发表**，两者分属不同权限域，务必在前期就说清（见 publishing.md 的路径预检）。

## 通用原则

- 失败汇报四件套：真实 code（含 `wechat_errcode`）、`retryable` 判断、`source_ip`（若有）、用户下一步具体动作或替代路径。
- 结果未知时查原操作，不换幂等键重发；`publish_id` 只代表已提交，不等于已发表。
- 只查询本人的操作和用量（`weixin_core_get_usage_summary`）。普通公众号运营不调用 weixin_admin 工具，
  安装技能不会提权。
