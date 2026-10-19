# 排版设计：按选题自动设计版式

没有固定模版。每篇文章由 Agent 按选题设计一份**设计方案**：调性定节奏，配色跟着选题走，
每个组件（刊头、标题、引语、卡片、分割线、图片框、步骤条、关注卡……）从样式库里各选一种，
做法和编辑器插件（如壹伴）的「样式中心 + AI 排版 + 样式换色」一样，只是选样式这一步由 Agent 按内容完成。

样式库是 `assets/styles.json`（唯一数据源）；渲染用 `scripts/build_article.py`（内部调用 `render_layout.py`）；
样式库之外还要手写的组件见 [editor-kit.md](editor-kit.md)。

## 何时进入本文件

- 定稿完成、准备渲染之前（版式在渲染前定下，不边写边改配色）。
- 用户提到风格、排版、配色、版式、「好看一点」「高级感」「科技感」「国风」等要求。
- 用户给了品牌色或 VI 要求，或要求与历史发文风格一致。

## 1. 设计方案由三层组成

| 层 | 决定什么 | 怎么选 |
|---|---|---|
| 调性 `mood` | 字号、行高、字距、段距，以及每个组件优先考虑哪几种样式 | 读者是谁、文章想让人有什么感觉；用户的风格词权重最高 |
| 配色 `palette` / `colors` | 主色和强调色；浅底、描边、深色块全部由主色派生 | 选题联想（节日、节气、行业、场景），其次是品牌色或账号历史主色 |
| 组件 `components` | 每个组件用哪种样式 | 调性给首选，再按文章结构修正（小标题数量、是否自带序号、步骤多少） |

调性不是成品模版：同一个调性配不同的选题颜色、不同的组件组合，出来的文章长得不一样。
三层可以独立替换，例如「东方雅致的节奏 + 重阳菊黄 + PART 式标题」。

## 2. 设计流程（Agent 自主完成，不停顿）

1. **读文章定方向**：一句话写出这篇的设计意图，例如「重阳敬老、写给子女看，要有节日感但不吵」。
2. **拿起点方案**：

   ```bash
   python3 scripts/render_layout.py 正文.md --auto [--hint "用户的风格原话"]
   ```

   输出 JSON 方案和每一项的理由（命中了哪些选题词、为什么换了标题样式）。
3. **按设计意图改方案**：脚本只认关键词，Agent 要用对选题的理解改它，常见要改的地方：
   - 配色：选题有明确的颜色联想却没命中时（例如写「银杏」「霜降」），从配色表里换，或直接给 `colors.primary`；
   - 组件：把会让这篇显得别扭的样式换掉（叙事文不用 `chip` 编号徽标，促销文不用 `center` 细线标题）；
   - 节奏：读者偏中老年、长文用 `density: large`，清单速查用 `compact`。
   方案只写要改的字段即可，其余自动补全：

   ```json
   {
     "mood": "oriental",
     "palette": "chongyang",
     "components": {"h2": "numeral", "figure": "frame", "ending": "ornament"},
     "density": "large"
   }
   ```

4. **渲染并留存方案**：

   ```bash
   python3 scripts/build_article.py 正文.md -o 成稿.html --design 方案.json --save-design 方案.json
   ```

   也可以不写文件，直接用参数：`--mood oriental --palette chongyang --set h2=numeral,figure=frame --density large`。
5. **生成对比页**：用这篇文章渲染 3 个可比方案（推荐方案 / 换调性 / 换配色），放进成稿确认卡：

   ```bash
   python3 scripts/render_layout.py 正文.md --design 方案.json --compare 方案对比.html
   ```

成稿确认卡里写：方案名、主色、一句设计意图、1–2 个备选和对比页（[interaction-cards.md](interaction-cards.md) 第 3 节）。
用户一句「换成 2」「标题换 PART 样式」「颜色再暖一点」就本地重渲染，不产生外部副作用。
只有用户点名要自己挑风格时，才出方案选择卡（[interaction-cards.md](interaction-cards.md) 第 5 节）。

## 3. 选题配色

`--auto` 会按选题词匹配下表，命中节日/节气时优先于行业色；完整列表和关键词用 `render_layout.py --list` 查看，
样式库预览页 `assets/style-gallery.html` 里有全部色卡。

| 类别 | 配色（id） |
|---|---|
| 节日 | 春节中国红 `spring-festival`、中秋桂金 `mid-autumn`、重阳菊黄 `chongyang`、端午艾绿 `dragon-boat`、清明青瓷 `qingming`、七夕玫红 `qixi`、国庆正红 `national-day`、圣诞松绿 `christmas` |
| 季节 | 春日嫩绿 `spring`、夏日湖蓝 `summer`、秋日枫橙 `autumn`、冬日雾蓝 `winter` |
| 科技与商业 | 科技蓝 `tech-blue`、未来紫 `cyber-violet`、安全藏蓝 `security-navy`、商务藏青 `business-navy`、金融墨蓝金 `finance-gold`、研究灰蓝 `research-slate` |
| 行业与生活 | 教育晴蓝 `edu-blue`、医疗青 `medical-teal`、自然绿 `eco-green`、薄荷青绿 `mint`、美食橘红 `food-orange`、旅行天蓝 `travel-sky`、童趣暖橙 `kids-orange`、玫瑰豆沙 `beauty-rose`、能量橙红 `sport-red` |
| 传播与叙事 | 活力促销红 `promo-red`、党政正红 `party-red`、陶土暖橙 `story-terracotta`、文艺雾霾蓝 `literary-haze`、杂志酒红 `editorial-wine`、东方黛绿朱砂 `oriental-ink`、极简墨黑 `ink-black` |

配色规则：

- **全文一个主色**，强调色只用在数字、序号、纹饰等关键位置；浅底、描边、深色块都由主色派生，不另造颜色。
- 表里没有合适的，就按选题联想直接给色值（`--primary`），例如「银杏」用 `#c9a227`、「海洋保护」用 `#1f6f8b`。
- 浅色（明黄、浅绿）当主色时，脚本会自动压暗后再当文字色用，并按对比度在色块上选黑字或白字；
  stderr 提示对比度偏低时，换更深的主色，不要无视。

### 品牌色与账号历史风格

- **品牌色**：`--primary "#1a3d6d" [--accent "#c8a45c"]`，所有组件一起换色（壹伴的「样式换色」），调性和组件照旧按选题选。
- **沿用历史风格**：用 `weixin_oa_list_published_articles`（带 `account_id`）取近期 3–5 篇，只对要比较的 ID 调
  `weixin_oa_get_published_article`，抽出主色、二级标题样式、是否用刊头/结论卡，写进方案（`colors.primary` + `components.h2` 等）。
  向用户说明「沿用了历史主色/标题样式」；这篇要换风格时明确说出来，不用「保持一致」掩盖改版。
- 品牌色或历史风格优先级高于选题联想：选题色只在账号没有固定视觉时才用。

## 4. 调性

调性只决定节奏和组件倾向。`--auto` 按用户风格词（`--hint`，权重最高）、选题信号词和结构特征
（分步骤、命令代码、多组百分比、活动时限、引语对话、长段落、节日）打分。

| 调性（id） | 节奏 | 首选组件 | 适合 |
|---|---|---|---|
| 稳重商务 `business` | 16px / 1.8 | 浅底刊头、左竖线标题、细边相框 | 行业解读、企业经营、方法论 |
| 理性科技 `tech` | 16px / 1.85 | 深色刊头、序号徽标标题、深色终端、阴影图 | AI/技术解读、产品发布、开发者内容 |
| 温暖叙事 `warm` | 17px / 1.95，宽字距 | 居中细线标题、居中引语、三点分隔、大圆角图 | 人物故事、品牌叙事、经历复盘 |
| 清爽干货 `fresh` | 16px / 1.85 | 下划线标题、浅底卡片、卡片式步骤 | 清单干货、效率技巧、攻略 |
| 深度评论 `editorial` | 16px / 1.9 | 杂志刊头、居中标题、加粗导语、END 收尾 | 深度长文、观点评论、年度复盘 |
| 严谨教程 `tutorial` | 16px / 1.8 | 序号徽标标题、竖线步骤、描边卡与按钮 | 教程、数据报告、原理拆解 |
| 活力促销 `promo` | 16px / 1.8 | 满底刊头、色块标题、大圆角按钮、框住的数字 | 活动报名、新品、限时福利 |
| 东方雅致 `oriental` | 16px / 2.0，宽字距 | 纹饰刊头、壹贰叁标题、纹饰分隔 | 传统文化、节气、文旅非遗 |
| 节庆喜庆 `festive` | 16px / 1.9 | 满底刊头、中文序号标题、纹饰收尾 | 节日祝福、节日活动、习俗科普 |
| 生活美学 `lifestyle` | 16px / 1.95，宽字距 | NO.01 标题、居中引语、大圆角图 | 生活方式、好物、读书观影、城市漫步 |

不要盲信第一名：前两名分数接近或内容跨领域（如「技术 + 活动」）时，按账号历史风格和本篇目标取舍，
在确认卡里点出另一个方向并附对比页。全部 0 分时脚本用稳重商务兜底，Agent 应按选题自己判断。

## 5. 组件样式库

`render_layout.py --gallery 样式库.html [--palette x | --primary #RRGGBB]` 生成每个组件全部样式的预览页
（已附 `assets/style-gallery.html`）。用 `--set 组件=样式` 或方案里的 `components` 指定。

| 组件 | 写法 | 样式 |
|---|---|---|
| 刊头 `masthead` | `:::masthead 栏目标签`，第一行大标题，其余行副题；有刊头时 `#` 标题不再重复 | `soft` 浅底左粗线 / `dark` 深色块 / `block` 主色满底 / `rule` 杂志上下线 / `ornament` 上下纹饰 |
| 二级标题 `h2` | `##` | `bar` 左竖线 / `underline` 下划线 / `chip` 序号徽标 / `part` PART 01 眉标 / `no` NO.01 大序号 / `numeral` 壹贰叁 / `center` 居中细线 / `block` 色块 / `pill` 胶囊 |
| 三级标题 `h3` | `###` | `color` 主色字 / `dot` 方块前缀 / `plain` 加粗 |
| 导语 `lead` | 首段自动作导语 | `muted` 次要色 / `bold` 加粗 / `boxed` 浅底框 |
| 引语 `quote` | `>` | `bar` 浅底左线 / `center` 居中大引号 / `soft` 浅底圆角 |
| 结论卡 `card` | `:::card` | `bar` / `border` / `soft` |
| 行动号召 `cta` | `:::cta` | `solid` / `outline` / `center` |
| 数字块 `stat` | `:::stat 数值 \| 注解` | `big` / `boxed` |
| 分割线 `divider` | `---` | `line` / `dots` / `short` 主色短线 / `ornament` 纹饰 |
| 图片 `figure` | `![图注](url)` | `plain` / `shadow` / `frame` / `round` |
| 命令/代码 `code` | `:::code 标签`，`$ ` 开头的行显示为命令提示符，不参与文字体检 | `soft` / `terminal` |
| 步骤条 `steps` | `:::steps 标签`，每行 `标题 \| 说明` | `timeline` 竖线串联 / `cards` 卡片 |
| 提示/注意 `callout` | `:::tip` / `:::warn`（注意卡会多占一个强调色） | `soft` / `line` |
| 关注卡 `follow` | `:::follow 账号名 \| 一句关注理由`，计作 CTA | `echo` 与刊头呼应 / `card` / `minimal` |
| 文末收尾 `ending` | 自动追加，有关注卡时放在关注卡之前 | `none` / `end`（— END —）/ `ornament` |

`chip`、`part`、`no`、`numeral` 自带序号；小标题本身已写了「1.」「第一」时，`--auto` 会自动换成不带序号的样式，
手动指定时也要避免重复编号。其他标题样式需要编号时在方案里写 `"numbered": true`。

组合原则（格式刷原则）：

- 同级元素只用一种样式，整篇看起来是一个人排的。
- 一篇用到的组件种类控制在 4–5 种；推广、教程类建议「刊头 + 步骤条 + 命令块 + 关注卡」，故事类通常只用刊头和图片框。
- 样式库覆盖不了的组件（对比卡、时间线、双图并排、往期推荐）按 [editor-kit.md](editor-kit.md) 手写 `:::html`，
  颜色从 `--print-tokens` 取，和方案保持一致。

## 6. 渲染输入格式

受支持的 Markdown 子集见 `assets/sample-article.md`：`#`/`##`/`###` 标题、段落（首段自动作导语）、
`-`/`1.` 列表、`>` 引语、`---` 分隔、`![说明](url)` 图片、上表的 `:::` 组件块，以及 `:::html`（原样嵌入手写组件）。
行内支持 `**加粗**`、`*斜体*`、`` `代码` ``。正文外链在公众号里通常不可点击，脚本会把外链列到 stderr，
需另行处理（放进「阅读原文」或用文字说明）。

配图的色调跟方案主色、质感跟调性走，见 [imagery.md](imagery.md) 第三步。

## 7. 出稿前自检

- [ ] 能用一句话说出这篇的设计意图，配色和组件都服务于它，而不是照搬 `--auto` 第一名。
- [ ] 配色和选题有关联（或是品牌色 / 历史主色），全文一个主色。
- [ ] 同级标题、同类卡片样式一致；带序号的标题样式没有和正文里的序号重复。
- [ ] 刊头、步骤、命令、提示、关注引导用的是组件块，不是各自手写一套样式。
- [ ] `check_html.py` 无 ERROR（强调色数量、禁用标签与样式、alt 都由它检查）。
- [ ] 方案已用 `--save-design` 存下，改稿和下一篇沿用时直接 `--design` 复用。
- [ ] 写入草稿后用 `weixin_oa_get_draft` 读回，确认微信改写后版式仍成立。
