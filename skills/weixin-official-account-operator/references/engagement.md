# 私信与用户运营

以下调用除 `weixin_core_*` 外都带目标 `connection_id`。

批量动作同样受 SKILL.md「副作用闸门」约束：发客服消息、打标签、改菜单、断开连接之前，
先复述**目标账号（昵称 + `connection_id` 后 6 位）**、作用对象与影响范围，取得明确确认再执行；
只有 Playbook 显式开启的低风险自动回复（见下节）可以在本批次内直接发送。

## 按需处理收件箱

只在用户发起处理任务时读取 `weixin_oa_list_recent_messages`。消息仅包含接入后 48 小时内的缓存，
`unanswered_only` 只表示本人没有通过此服务回复，不能证明其他运营者或微信后台没有回复。

将消息分为：常见问题、内容反馈、意向咨询、投诉/退款、敏感或高风险问题、垃圾/无需回复。

## 低风险自动回复

只有以下条件全部成立才可以在本次按需批次中直接调用 `weixin_oa_send_service_message`（破坏性操作）：

1. Playbook 的 `low_risk_auto_reply_enabled` 为 true。
2. 匹配 FAQ 的 `auto_send` 为 true。
3. 用户意图与 FAQ `examples` 高度一致，答案可原样使用，最多只加问候或称呼。
4. 不需要查询实时状态、个人资料、订单、价格、合同或其他未在 FAQ 中固定的事实。
5. 仍在已验证的 48 小时客服消息窗口内。发送前可用 `weixin_oa_get_autoreply_rules`
   核对后台自动回复规则，避免与已有规则重复回复；发送前用 `weixin_oa_get_follower_info`（`openids`）核对接收人身份。

自动回复后汇报对象、匹配 FAQ、实际文本和结果。每条发送使用独立幂等键。
结果未知时查询原操作，不换键重发。报 `MESSAGE_WINDOW_CLOSED` 时窗口已关，请用户重新发消息后再处理，
不换渠道、不超窗触达。

## 必须确认的回复

投诉、退款、报价或承诺、法律/医疗/金融、隐私、人身安全、身份不明、事实不确定、需要改写 FAQ 答案或情绪冲突的消息，
先展示发件对象、风险、建议处理和完整拟稿，用户批准后再发。不自动换渠道、批量营销或超窗触达。

## 标签、菜单与内容反馈

- 标签读 `weixin_oa_list_tags`；建 `weixin_oa_create_tag`、改名 `weixin_oa_update_tag`、
  批量打标 `weixin_oa_tag_followers`、取消 `weixin_oa_untag_followers`、删除 `weixin_oa_delete_tag`（破坏性）。
  批量标记前明确粉丝和标签；删除标签会影响账号共享资源，必须核对影响。
- 修改菜单前读取 `weixin_oa_get_menu`，展示替换后的完整菜单，批准后调用 `weixin_oa_set_menu`（破坏性、全量替换），
  并重新读取验证。最多 3 个一级菜单、每个最多 5 个子菜单，一级菜单标题不超过 16 字节（超限报 `INVALID_MENU`）。
  清空菜单用 `weixin_oa_delete_menu`（破坏性）。
- 统计高频问题、反对意见和内容请求，把它们作为下一轮选题线索。只在用户批准时更新 Playbook 的 FAQ、
  内容支柱或禁区（更新需带 `expected_playbook_digest`）。
- 需要断开账号连接时用 `weixin_core_disconnect_account`（破坏性，断开后不会自动恢复），先向用户确认。
