# 排版与发布

## 0. 按需路径预检（承诺交付方式之前做）

不要等到最后一步才发现路走不通。**在动笔之前**（或首次交付之前）用只读调用摸清这个账号能走到哪一步，
把结论先告诉用户，再承诺交付方式。预检用只读接口，副作用最小，**每一项都带上目标 `connection_id`**。
**只探本次要走到的环节，且互不依赖的探测并行发出**：只写草稿就探 `list_drafts`（+ 有配图时探图片链路）；
要预览才加 `list_followers`；要发表才提前告知“发表与草稿分属不同权限域”，以 `list_followers` 结果作参考；
纯本地写作/改稿阶段不做任何预检。

| 探测 | 通过意味着 | 失败意味着 |
|---|---|---|
| `weixin_core_list_accounts` | 连接正常、能拿到 `connection_id`/`mode` | 需重新授权 |
| `weixin_oa_list_drafts` | 草稿可读写 | 40164（白名单）或资质问题 → [recovery.md](recovery.md) |
| `weixin_oa_list_materials` | 素材可读写 | 同上 |
| `weixin_oa_list_followers` | 用户管理族有权限 | 多为 48001 → **预览（需 openid）和发表（freepublish）通常同族受限** |
| `weixin_oa_upload_content_image`（一张第三方图） | 图片链路可用 | 见下面「图片链路故障」 |

三条铁律：

1. **工具实现可用 ≠ 账号有权限。** 服务能力清单里写 `implemented` 只说明代码写完了，账号可能一个都调不通。
   `mode=direct`（配置直连）账号的 `scopes` 为空，实际权限由微信返回决定，预检必须以实测结果为准。
2. **能写草稿 ≠ 能发表。** 草稿读写和发表分属不同权限域，很多未认证号卡在这里。预检阶段就要说清，
   不要让用户走到最后一步才被告知“发表不了”。
3. **不要继承上一次的故障结论。** 同一条链路可能上一轮 `INVALID_IMAGE`、下一轮 `40005`、再下一轮恢复正常。
   每轮任务都重新做一次轻量探测，别把历史判断当成永久结论。

错误码的完整含义与处置统一见 [查询与恢复](recovery.md)，本文件只在场景内给出最短路径。

## 1. 两阶段交付：本地迭代 → 最终确认后一次性执行

**改稿不要动线上资源。** 用户每提一条修改意见就重新部署图床、重新上传图片、重新写一次草稿，
既浪费配额又会污染草稿箱。分成两段：

**阶段 A（自由，可反复，不联网）**

1. Markdown 定稿后一条命令 `scripts/build_article.py 正文.md -o out.html` 完成体检（ERROR 清零才渲染）+ 主题推荐 + 渲染；
2. 在本地打开 HTML 给用户看真实版式；
3. 按 [配图规划](imagery.md) 生成图片并用 `scripts/prepare_image.py` 本地处理达标；
4. 需要修改就在本地改，改到第 N 版都不产生任何外部副作用。

**阶段 B（需确认，一次性走完）** —— 用户明确说“入草稿箱 / 就这样发 / 可以了”之后才启动：

1. 图片一次性备齐后**部署一次**取得公网 HTTPS 地址；
2. 上传封面与正文图，取得 `media_id` 和 mmbiz URL；
3. 首次写入用 `weixin_oa_create_draft`，后续修改一律 `weixin_oa_update_draft`；
4. 用 `weixin_oa_get_draft` 读回核对并记录 `draft_digest`。

**阶段 C（需最终确认，对外可见）** —— 微信预览（给真人发消息）和发表，逐条复述后执行，见下文。

### 资源复用表（阶段 B 之后保留在对话里）

| 资源 | 标识 | 复用规则 |
|---|---|---|
| 正文图 | mmbiz URL | 同一张图不重复上传；换掉哪张才重传哪张 |
| 封面 | `media_id` | 不换封面就沿用；换封面才重新 `add_material` |
| 草稿 | `media_id` + `draft_digest` | 改文字走 `update_draft`，不新建草稿 |
| 图床目录 | 公网 URL 前缀 | 同一目录不重复部署；要改图就一次改齐再部署一次 |

只改文字 → 只 `update_draft`（新的 `idempotency_key`），图片资源全部复用。
换账号 → 复用表整表作废，回到第 0 节重新预检（见 SKILL.md「账号锁定」）。

### 执行前确认清单（阶段 B/C 都要先摆出来）

```text
即将执行，请确认：
- 账号：<昵称/主体>（connection_id 后 6 位 …abc123）
- 动作：创建草稿 / 更新草稿 / 微信预览 / 发表
- 内容：标题…；摘要…；正文版本（微信读回版）
- 资源：封面 1 张（新传/复用）、正文图 N 张（M 张新传、K 张复用）
- 影响：公网部署会覆盖该目录既有线上内容；草稿写入后旧 digest 与旧批准失效
```

## 排版策略

**主题（配色 + 版式骨架）先按 [主题风格模版](themes.md) 定下来，再回到本节处理图片、草稿和发表。**
用户偏好的版式映射到主题 id：`professional`→`professional`、`knowledge`→`academic`、
`story`→`warm`；用户给了品牌色时用 `--primary` 从最接近的主题派生。
渲染统一走 `scripts/build_article.py`（内部调用 `render_theme.py`，自动推荐主题 → 输出微信安全的内联样式 HTML），不要每次手写 HTML。

未配置品牌颜色时选一个与主题相符的低饱和强调色，全文仅用一个主强调色。正文 15–17px、行高 1.7–1.9、
文字 `#333333`、段后距 16–20px，二级标题 18–22px。颜色、粗体、大字、背景和下划线不同时堆叠。

图片不可用时，用纯 CSS 视觉块制造层次而不撒谎：导语卡、对照卡（痛点灰底 vs 结论主色底）、
强调数字（24–28px + 居中小字注解）、分隔符（如 ◆ ◆ ◆）、CTA 卡。

## HTML 约束

- 使用单栏结构和内联 `style`，优先 `section`、`p`、`h2`、`strong`、`blockquote`、`ul`/`ol` 和 `img`。
- 不依赖外部 CSS、JavaScript、动画、表单、iframe、SVG、Flex/Grid 或绝对定位。微信仍可能进一步清理样式。
- 不使用事件属性、`script`、`iframe`、`object`、`embed`、`form`、`base` 或 `svg`；
  链接只使用 HTTP(S)；CSS 不使用 `url()`、`@import`、`expression` 或 `behavior`。
- 图片样式使用 `display:block; width:100%; height:auto; margin:24px auto;`，并提供有意义的 `alt`。
- 最多 8 篇图文；标题最多 32 字、作者 16 字、摘要 120 字；正文最多 19,999 字且 UTF-8 体积小于 1MB。

不使用脚本时的兜底骨架（脚本已内置 8 套主题骨架，优先用脚本渲染）：

```html
<section style="max-width:100%;padding:0 16px;color:#333333;font-size:16px;line-height:1.8;box-sizing:border-box;">
  <p style="margin:0 0 20px;color:#666666;">导语</p>
  <h2 style="margin:32px 0 16px;padding-left:12px;border-left:4px solid #56728f;font-size:20px;line-height:1.4;">小标题</h2>
  <p style="margin:0 0 18px;text-align:justify;">正文</p>
  <section style="margin:24px 0;padding:16px;background-color:#f6f7f8;color:#555555;">重点结论</section>
  <img src="WECHAT_IMAGE_URL" alt="图片说明" style="display:block;width:100%;height:auto;margin:24px auto;" />
</section>
```

## 图片：生成 → 处理 → 托管 → 上传

### 生成后先跑脚本

`weixin_oa_upload_content_image` 和 `weixin_oa_add_material` **只接受 `image_url`**，由服务端下载后再转交给微信，
没有本地文件、base64 或 multipart 通道。因此图片必须先成为公网 HTTPS 资源。

统一用脚本处理，不要每次手写 Pillow 代码（**必须串行调用**，并发会因输出文件名按秒生成而互相覆盖）：

```bash
PY=python3   # 没有 Pillow 时先 python3 -m pip install pillow
$PY scripts/prepare_image.py 原始图1.png 原始图2.png -o ./wx_images    # 去水印 → ≤1080px → 压到 <200KB
$PY scripts/prepare_image.py ./wx_images --check-only                  # 自检：格式/体积/宽度
```

脚本会裁掉生成图自带的水印（默认顶部 2%、底部 9%）、限制宽度、二分质量压到目标体积，
并输出 JPEG 魔数与达标情况。生成 prompt 里另外明确写 `no text, no letters, no logos, no watermarks`，
避免图上出现乱码文字。脚本不达标时不要硬传，先换图或换参数。

### 上传前先判定链路故障性质

任何服务端环节的失败都会统一体现在这两个工具上，只能靠对照测试分层：
拿一个第三方可信地址（如 `https://www.python.org/static/img/python-logo.png`）做对照测试，据此定位故障层。

注意两种图片错误不同：`INVALID_IMAGE_URL` 是地址本身不合规（非 HTTPS 公网地址或带用户信息），
`INVALID_IMAGE` 是服务端取图失败或被判不安全。完整错误码见 [recovery.md](recovery.md)。

| 现象 | 说明 | 处置 |
|---|---|---|
| 第三方图也失败，报 `INVALID_IMAGE`「目标地址不安全」 | 服务端出网被拦，请求根本没到微信 | 走手动通道；不建议反复重试 |
| 第三方图也失败，报 `40005` / `40113` | 请求到了微信，服务端 multipart 组装有问题 | 同上，并把错误码+对照证据整理给用户去报障 |
| 只有我们的图失败 | 图片或托管地址问题 | 检查 magic bytes、体积、`Content-Type`、URL 是否 200 |

### 托管与部署

图片必须有**公网 HTTPS 地址**。本地准备好静态目录后，用当前环境可用的静态托管发布取得域名再用
（对象存储、GitHub Pages、或客户端自带的部署工具均可；不限定具体工具）。

部署属于外部副作用，三条约束：

1. **只在阶段 B 部署一次**——配图全部定稿后再部署，不每次微调都重新发布；
2. **向已有分享链接部署更新会覆盖线上内容**，部署前先取得用户确认，一次改齐再发；
3. 已部署过的 URL 前缀直接复用，同一张图不重复上传（见资源复用表）。

### 手动通道（图片链路不通时的兜底）

生成带 `<img>` 的完整版 HTML，在浏览器中打开，让用户全选（⌘A / Ctrl+A） → 复制 → 粘进公众号后台编辑器，
后台会自动抓取上传图片；封面在后台单独上传设置。**不要谎称图已经进草稿了。**

## 草稿写入与核对

1. 正文图调用 `weixin_oa_upload_content_image`（返回正文可用的 mmbiz URL），封面调用 `weixin_oa_add_material`（返回 `media_id`）。
   **只上传这次真正新增或换掉的图**，已在复用表里的 URL/`media_id` 直接沿用。
2. 封面 `media_id` 写入 `thumb_media_id`；正文图 URL 写入 HTML。
3. 新文章用 `weixin_oa_create_draft`；**同一篇文章的后续修改一律 `weixin_oa_update_draft`**
   （指定 `media_id` 和从 0 开始的文章 `index`），不反复新建草稿。
4. 每次写入都用独立稳定的 `idempotency_key`。同一请求重传保持原键和参数；内容或目标变化后换新键。
5. 图片插在**语义对应**的段落之后（如“客服场景”段后配客服图），不要堆在开头或全放文末。
6. 全程带上目标 `connection_id`。

**微信会改写 HTML，这是正常的，别误判失败：**

- `<img src>` → `<img data-src="https://mmbiz.qpic.cn/.../640?from=appmsg">`
- 可能丢掉部分 style、`alt` 被保留
- `<br>` 可能变成 `<br  />`

核对时以“图片地址变成 mmbiz 的 https 地址且仍存在”为通过标准。

## digest 规则

- 每次成功写入草稿，`draft_digest` 都会变化。
- 任何内容改动（含插图、改摘要、换封面）都会让**旧 digest、旧预览、旧发表批准全部失效**。
- `weixin_oa_publish_draft` 必须传最新的 `expected_draft_digest`（从最近一次 `weixin_oa_get_draft` 拿）；
  传错会被拒绝并报 `CONTENT_CHANGED`，这是防呆机制，不是 bug——重新读取、重新取得批准即可。

## 预览

预览属于**对外动作**（会给真人发一条消息），先复述账号与接收人、取得确认再发；
草稿还没建立时只能给本地 HTML 预览，不存在“先预览再写草稿”的顺序。

1. 调用 `weixin_oa_preview_draft` 前必须明确接收人；返回 `CAPABILITY_UNVERIFIED` 表示该部署未开启预览。
2. `preview_draft` 需要 `recipient_openid`。取 openid 的顺序：`weixin_oa_list_followers` →
   若返回 48001（很常见），请用户给公众号发一条消息，再查 `weixin_oa_list_recent_messages` 取返回中的用户标识。
   两条路都拿不到，就不要猜。拿到后可用 `weixin_oa_get_follower_info`（`openids` 数组）核对是不是本人。
3. **拿不到 openid 或预览未开启时，用 `weixin_oa_get_draft` 返回的 `url`**
   （带 `tempkey` 的 `mp.weixin.qq.com/s?...`）作为预览——微信内打开可见真实排版，但要提醒**有时效**。
   同时可以在本地打开所见即所得的 HTML 给用户看版式。
4. 明确告知用户是否真的发送了微信预览，不要把本地预览说成微信预览。

## 发表

1. 发表前必须展示：目标账号（昵称/主体 + `connection_id` 后 6 位）、标题、摘要、封面、
   微信实际保存的正文（读回版本），取得明确批准。批准只对当前 `draft_digest` 有效，
   内容一改就失效。
2. 批准后调用 `weixin_oa_publish_draft`（带最新 `expected_draft_digest`），再用 `weixin_oa_get_publish_status` 查终态。
3. 只有微信返回成功才算“已发表”。`publish_id` 只代表已提交。
4. **发表不是群发**，不承诺向所有粉丝推送。

### 发表被 48001 拦住时

账号资质限制（常见于未认证订阅号/个人主体），错误码为 `INSUFFICIENT_SCOPE`（`wechat_errcode` 48001 或 61007），
重新授权也拿不到，重试无意义。如实交付并给替代路径：

- 草稿已在草稿箱中（给出 `media_id` 和正文校验结果），用户在后台点群发即可，**效果与发表接口一致**；
- 提醒用户在后台确认封面和配图；
- 说明打通一键发表需要微信认证（个人主体不可认证，企业/组织主体 300 元/年）。

不要含糊其辞地说“已发布”，也不要让用户以为是自己操作有误。
