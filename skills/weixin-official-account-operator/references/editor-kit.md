# 编辑器能力：Agent 直写 HTML 的排版、样式、配图与 AI 文案

编辑器插件（如壹伴）提供的样式库、一键排版、格式刷、图片样式、AI 标题和 AI 摘要，
在这里都由 Agent 直接写出微信安全的 HTML 完成，不需要用户装插件，也不用在后台逐个点样式。
产出的 HTML 既能写入草稿，也能整段复制进公众号编辑器。

## 何时进入本文件

- 用户要「样式丰富一点」「像壹伴那样排版」「加个关注引导 / 往期推荐 / 分割线 / 金句卡」。
- 主题渲染出的版式不够用，需要对比卡、步骤条、时间线、双图并排等组件。
- 用户给了一篇现成文章（或已发文章）要「一键排版」「重新排一下」。
- 需要摘要、导语或标题的多版本候选。

## 1. 两条出稿路线，按需选

| 路线 | 适合 | 做法 |
|---|---|---|
| A. Markdown + 主题渲染（默认） | 常规图文，一套主题从头到尾 | 写 Markdown → `build_article.py`，见 [themes.md](themes.md) |
| B. Markdown + 手写组件 | 主题版式外还要几处特殊组件 | 在 Markdown 里用 `:::html` 围栏块插入下面的组件，其余照常渲染 |
| C. 整篇直写 HTML | 高度定制的专题、活动页、重排现成文章 | 按本文件组件拼整篇，跑 `check_html.py` |

三条路线都以主题 token 为唯一配色来源，组件里的 `{primary}` 等占位换成该主题的实际色值：

```bash
python3 scripts/render_theme.py 正文.md --theme tech --print-tokens -o /tmp/ignore.html
```

路线 B 的写法：

```markdown
:::html
<section style="margin:24px 0;padding:14px 16px;background-color:#eef3f9;border-radius:6px;">……</section>
:::
```

`:::html` 块原样输出，不参与文字体检；`build_article.py` 渲染后会自动跑 `check_html.py --strict`，有 ERROR 时返回失败。
路线 C 写完手动跑：

```bash
python3 scripts/check_html.py 成稿.html --preview 预览.html   # 本地体检 + 375px 手机预览
python3 scripts/check_html.py 成稿.html --final --strict       # 入草稿前：图片必须已换成微信图片地址
```

## 2. 一键排版：全局参数与文字规范

用户说「一键排版」「排得舒服点」时，按主题 token 统一以下参数，不逐段微调：

| 项 | 默认 | 说明 |
|---|---|---|
| 正文字号 / 行高 | 15–17px / 1.75–1.9 | 取主题 `font_size`、`line_height` |
| 字间距 | 0.3–1px | 取主题 `letter_spacing`；人文类可放宽到 1px |
| 段后距 | 16–20px | 段与段之间用段后距，不用空段落撑开 |
| 页边距 | 外层 `padding:0 16px` | 图片可通栏（外层不加边距时用 `width:100%`） |
| 对齐 | 两端对齐 `text-align:justify` | 公众号习惯不首行缩进；用户明确要求时才加 `text-indent:2em` |
| 正文色 | `#333333` / 次要 `#666666` | 不用纯黑 |

文字规范（排版时顺手改，改完告诉用户改了哪几类）：

- 中文与英文、数字之间加一个半角空格（`用 AI 写周报`、`3 个坑`），数字与单位之间不加（`20%`、`5km`）。
- 中文语境用全角标点，不混用 `,` `.` `?`；省略号用 `……`，破折号用 `——`。
- 连续感叹号、问号只留一个；全文感叹号控制在关键处一两次。
- 清除外来格式：用户粘贴的稿子里，残留的字体、颜色、背景、`class`、`id`、空段落一律去掉，再按主题重排。

## 3. 样式库（微信安全组件）

全部只用 `section` / `p` / `span` / `strong` / `img` 和内联 `style`；不用 Flex/Grid、定位、`class`、SVG。
并排用 `display:inline-block` + 百分比宽度。每个组件在同一篇里**只用一种样式**（格式刷原则：
同级标题、同类卡片长得一模一样）。一篇里组件种类不超过 4–5 种，多了就乱。

### 3.1 标题

```html
<!-- 左竖条 -->
<h2 style="margin:32px 0 16px;padding-left:10px;border-left:4px solid {primary};font-size:19px;line-height:1.4;color:{text};">小标题</h2>

<!-- 序号 + 标题 -->
<section style="margin:32px 0 16px;">
  <span style="display:inline-block;padding:2px 10px;background-color:{primary};color:#ffffff;font-size:15px;font-weight:bold;border-radius:4px;">01</span>
  <span style="display:inline-block;margin-left:8px;font-size:18px;font-weight:bold;color:{text};vertical-align:middle;">小标题</span>
</section>

<!-- 居中双线 -->
<section style="margin:36px 0 18px;text-align:center;">
  <p style="margin:0;font-size:18px;font-weight:bold;color:{text};letter-spacing:2px;">小标题</p>
  <p style="margin:6px auto 0;width:40px;height:2px;line-height:2px;font-size:0;background-color:{primary};">&nbsp;</p>
</section>

<!-- 下划线高亮 -->
<h2 style="margin:32px 0 16px;font-size:18px;line-height:1.4;color:{text};"><span style="border-bottom:6px solid {primary_soft};">小标题</span></h2>
```

### 3.2 金句与引用

```html
<!-- 金句卡：全篇最值得截图的一句话，最多 1–2 处 -->
<section style="margin:28px 0;padding:20px 22px;background-color:{primary_soft};border-radius:8px;text-align:center;">
  <p style="margin:0;font-size:17px;line-height:1.7;font-weight:bold;color:{primary};">一句可以被截图转发的话</p>
</section>

<!-- 引用：原话、他人观点、出处 -->
<section style="margin:20px 0;padding:12px 16px;border-left:3px solid {primary_line};background-color:{bg_soft};">
  <p style="margin:0;font-size:15px;line-height:1.75;color:{text_muted};">引用的原话</p>
  <p style="margin:6px 0 0;font-size:13px;color:{text_muted};text-align:right;">—— 出处</p>
</section>
```

### 3.3 重点与提示

```html
<!-- 重点卡（带标签） -->
<section style="margin:24px 0;padding:16px 18px;border:1px solid {primary_line};border-radius:6px;">
  <p style="margin:0 0 8px;font-size:14px;font-weight:bold;color:{primary};">划重点</p>
  <p style="margin:0;font-size:15px;line-height:1.75;color:{text};">要点内容</p>
</section>

<!-- 提示 / 注意：注意类用低饱和的暖色底，不用大红 -->
<section style="margin:20px 0;padding:12px 16px;background-color:#fff8e6;border-radius:6px;">
  <p style="margin:0;font-size:14px;line-height:1.7;color:#8a6d3b;"><strong>注意：</strong>容易做错的一步</p>
</section>

<!-- 行内高亮：只给关键短语，一段最多一处 -->
<span style="background-color:{primary_soft};color:{primary};padding:0 2px;">关键短语</span>
```

### 3.4 对比、数字与步骤

```html
<!-- 对比卡：之前 / 之后，两列并排 -->
<section style="margin:24px 0;font-size:0;">
  <section style="display:inline-block;width:48%;margin-right:4%;vertical-align:top;padding:14px;box-sizing:border-box;background-color:{bg_soft};border-radius:6px;">
    <p style="margin:0 0 6px;font-size:14px;font-weight:bold;color:{text_muted};">之前</p>
    <p style="margin:0;font-size:14px;line-height:1.7;color:{text_muted};">痛点描述</p>
  </section><section style="display:inline-block;width:48%;vertical-align:top;padding:14px;box-sizing:border-box;background-color:{primary_soft};border-radius:6px;">
    <p style="margin:0 0 6px;font-size:14px;font-weight:bold;color:{primary};">之后</p>
    <p style="margin:0;font-size:14px;line-height:1.7;color:{text};">改变后的结果</p>
  </section>
</section>

<!-- 数字卡：一个数字 + 一句注解；数字必须真实 -->
<section style="margin:28px 0;text-align:center;">
  <p style="margin:0;font-size:30px;font-weight:bold;line-height:1.2;color:{primary};">3 天</p>
  <p style="margin:6px 0 0;font-size:13px;color:{text_muted};">从提需求到上线</p>
</section>

<!-- 步骤 / 时间线：左侧竖线串起来，每步一块 -->
<section style="margin:24px 0 24px 8px;padding-left:16px;border-left:2px solid {primary_line};">
  <section style="margin:0 0 16px;">
    <p style="margin:0 0 4px;font-size:15px;font-weight:bold;color:{primary};">第 1 步｜标题</p>
    <p style="margin:0;font-size:15px;line-height:1.75;color:{text};">说明</p>
  </section>
  <section style="margin:0;">
    <p style="margin:0 0 4px;font-size:15px;font-weight:bold;color:{primary};">第 2 步｜标题</p>
    <p style="margin:0;font-size:15px;line-height:1.75;color:{text};">说明</p>
  </section>
</section>
```

### 3.5 分割线

```html
<!-- 细线 -->
<section style="margin:32px 0;height:1px;line-height:1px;font-size:0;background-color:{divider};">&nbsp;</section>
<!-- 符号 -->
<p style="margin:32px 0;text-align:center;font-size:12px;letter-spacing:12px;color:{primary_line};">◆◆◆</p>
<!-- 短线居中 -->
<p style="margin:32px auto;width:60px;height:2px;line-height:2px;font-size:0;background-color:{primary};">&nbsp;</p>
```

### 3.6 图片样式

```html
<!-- 圆角 + 轻阴影 + 图注 -->
<section style="margin:24px 0;text-align:center;">
  <img src="WECHAT_IMAGE_URL" alt="图片说明" style="display:block;width:100%;height:auto;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.08);" />
  <p style="margin:8px 0 0;font-size:13px;line-height:1.6;color:{text_muted};">图注：写图里没有的信息</p>
</section>

<!-- 双图并排（截图对比、前后对照） -->
<section style="margin:24px 0;font-size:0;">
  <img src="WECHAT_IMAGE_URL_1" alt="左图说明" style="display:inline-block;width:49%;margin-right:2%;height:auto;vertical-align:top;border-radius:6px;" /><img src="WECHAT_IMAGE_URL_2" alt="右图说明" style="display:inline-block;width:49%;height:auto;vertical-align:top;border-radius:6px;" />
</section>

<!-- 描边相框：人物、产品图 -->
<img src="WECHAT_IMAGE_URL" alt="图片说明" style="display:block;width:100%;height:auto;margin:24px auto;padding:6px;box-sizing:border-box;border:1px solid {primary_line};border-radius:4px;" />
```

GIF 动图：正文图片上传接口通常只接受 JPG/PNG，上传被拒时如实告诉用户，请其在公众号后台编辑器里插入；
一篇最多一两张，照顾手机流量。

### 3.7 文末组件

```html
<!-- 关注引导：一句理由 + 一个动作，不写「点赞在看转发三连」堆砌 -->
<section style="margin:36px 0 20px;padding:18px;background-color:{primary_soft};border-radius:8px;text-align:center;">
  <p style="margin:0 0 6px;font-size:16px;font-weight:bold;color:{primary};">关注「账号名」</p>
  <p style="margin:0;font-size:14px;line-height:1.7;color:{text_muted};">每周一篇，讲清一个可以直接用的方法</p>
</section>

<!-- 往期推荐：只放本号已发文章，链接用 mp.weixin.qq.com 的文章地址 -->
<section style="margin:28px 0;">
  <p style="margin:0 0 10px;font-size:15px;font-weight:bold;color:{text};">往期推荐</p>
  <p style="margin:0 0 8px;font-size:14px;line-height:1.6;"><a href="https://mp.weixin.qq.com/s/xxxx" style="color:{primary};text-decoration:none;">· 往期文章标题一</a></p>
  <p style="margin:0;font-size:14px;line-height:1.6;"><a href="https://mp.weixin.qq.com/s/yyyy" style="color:{primary};text-decoration:none;">· 往期文章标题二</a></p>
</section>

<!-- 作者 / 签名 -->
<p style="margin:24px 0 0;font-size:13px;line-height:1.7;color:{text_muted};text-align:right;">文｜作者名　编辑｜编辑名</p>
```

往期推荐的标题和链接只从 `weixin_oa_list_published_articles` 读回（带 `account_id`），不编造链接；
读不到就不放这个组件。二维码图片由用户提供，按图片流程上传后再放。

## 4. AI 标题、摘要与导语

- **标题**：按 [editorial.md](editorial.md) 第 4 节出 3–5 个不同句式的候选，`score_title.py` 评分后默认用推荐项，备选进成稿确认卡；用户要求时才出标题卡。
- **摘要（digest）**：默认写一版、备一版进确认卡（用户要求时出 2–3 版供选），最多 120 字；转发卡片和消息列表只显示开头一部分，
  所以**开头一句要能单独成立**。三版分别侧重：读者收益、悬念、核心结论；不复述标题，不用「本文介绍了」。
  用户不填摘要时微信会截取正文开头，开头若是图片或寒暄会很难看，所以总是给一版。
- **导语**：正文第一段 60–120 字，进入场景、冲突或结论；路线 A 中首段自动渲染为导语样式。
- AI 改写、续写、扩写、缩写、润色按 [voice.md](voice.md) 第 5 节，不另起一套。

## 5. 配图与封面

配图规划见 [imagery.md](imagery.md)。编辑器层面补充两点：

- **封面双规格**：同一张封面要同时适配 2.35:1（消息列表大图）和 1:1（转发卡片、次条小图），
  主体放在画面中间偏上的 1:1 安全区内。处理时用 `prepare_image.py --cover` 一次输出两个裁切版本，
  分别检查缩略后主体是否清晰。
- 正文里的图片样式用本文件 3.6 的组件，同一篇只用一种圆角和阴影。

## 6. 重排现成文章（采集 / 一键重排）

1. 来源只能是用户自己的稿子、本号已发文章（`weixin_oa_get_published_article`）或用户明确有权使用的内容；
   别人的文章只用来学习结构（见 [benchmarking.md](benchmarking.md)），不整篇搬运。
2. 先抽出纯文字和图片地址，丢掉原有样式，再按本文件第 2 节和所选主题重排；
   本号已发文章里的 mmbiz 图片地址可以复用，不重复上传。
3. 重排后给出改动前后对照：改了哪些版式、哪些文字规范，正文措辞不动（要改写另说）。

## 7. 出稿前自检

- [ ] `check_html.py` 无 ERROR；入草稿前用 `--final` 再跑一次。
- [ ] 组件种类 ≤ 5 种，同类组件样式一致；全文一个主强调色。
- [ ] 金句卡、高亮、数字卡都有真实内容支撑，没有为了好看硬加。
- [ ] 往期推荐、二维码、作者信息都来自真实数据或用户提供。
- [ ] 本地 375px 预览看过一遍，没有挤压变形的并排块；告诉用户最终以微信读回版本为准。
