# 视频模板总库（编号）

**所有视频模板都在这一张表里**（Tony 2026-11-06：模板归到一块儿，以后直接按编号调用）。模板文件分在两个仓库：
- `Tony11081/douyin-editor` 的 `templates/`（下表没写仓库的都在这里）
- `Tony11081/video-drop` 的 `templates/`（表里写了「video-drop」的）

Tony 选模板只说编号（2026-11-18 起共 1–79 号 + 51b）。样张页：templates_page.html（Claude 页面「Etsy-Tony 视频模板库」）。

## 一、每天在用的固定方向（先看这里）

每个方向的模板和配音固定，不混用。配音一律只加速配音（tts speed），画面、素材、音乐保持原速。

| 方向 | 账号 / 用途 | 时间（自动任务） | 模板 | 配音 | 背景音乐 |
|---|---|---|---|---|---|
| Etsy 政策速递 | Shopwright，讲新规 + 观点 | 每天 08:37 | 56 号（video-drop `templates/policy-brief/`） | Bo 男声 1.3 倍 | mixkit_driving_ambition 0.1 |
| 网站功能宣传 | openaigrowth.com 的工具和服务 | 每天 09:23 | 51b 号（`templates/promo-day/`） | ~~Lan~~ 已禁用（2026-11-06）；2026-11-13 图片去属性那条用 ElevenLabs Will，1.3 倍 | mixkit_dreaming_big 0.07 |
| Etsy 知识点 | 抖音 Etsy-Tony，常青知识 | 每天 15:47 | 52–55 号轮换（`templates/explainer/`） | Bo 男声 1.3 倍 | mixkit_driving_ambition 0.1 |
| AI浪潮 | 视频号 AI浪潮，每日 AI 新闻 | 早上（见 README） | 57 号（`templates/ai-wave/`） | 见 README | 见 README |
| TonyBook 跨境实操 | 抖音 助理－TonyBook跨境 | — | 60 号（video-drop `templates/tonybook-mag/`） | ElevenLabs Will | 见 README |
| 移轴微缩 | 抖音 Etsy-Tony 特别篇 | — | 58 号（video-drop `templates/etsytony-miniature/`） | 见 README | 合成音效 |
| 科普治愈 | 科学现象 → 人生道理 | — | 59 号（video-drop `templates/science-healing/`） | 见 README | 见 README |

所有方向共用的规矩（智能体总说明见仓库根目录 AGENTS.md）：
- **抖音遮挡安全区**：竖版底部 1460 以下、右侧 930 以右 860–1600、顶部 0–200 会被抖音界面盖住，字幕/重点字/人脸不放进去（详见 templates/creator-pack/README.md）。
- **不重复**：政策速递、知识点、网站宣传三条线共用选题台账 video-drop `templates/policy-brief/topics.md`，同一个知识点只做一次；TonyBook 也先读它。
- **免费实拍素材**：每条都要有，而且要和模板融为一体（素材在模板「下面」透出来，模板的暗角 / 颗粒 / 文字盖在上面）。Mixkit 只用详情页写「Mixkit Stock Video Free License」的，Pexels / Pixabay 也可以。已核对可商用和受限的清单见 `templates/explainer/README.md`。
- **网址**：画面右上角和结尾卡带 openaigrowth.com（49–55、51b 已内置）。
- **合成方式**：模板渲染成透明 webm（`?hole=1`），推到 video-drop 用提交 SHA 的 raw 链接；剪辑服务器 render 时素材在下、透明层在上；最后 mux 加配音和音乐。做法见 `templates/cinema/README.md`、`templates/explainer/README.md`、`templates/promo-day/README.md`。

## 二、全部模板编号
gallery.html 是所有模板的静态样式（?tpl=<代号>&s=hook|card，背景放 bg/hook.jpg、bg/card.jpg）。

| 号 | 名称 | 代号 | 动画版实现 |
|---|---|---|---|
| 1 | 立体大字（背后抠像大字） | — | assets/promo23/overlay_tpl.html（behind + front 两层） |
| 2 | 纪录片 | d | templates/docu/docu_tpl.html（05 车上道歉在用） |
| 3 | 资讯快报 | n | templates/news/news_tpl.html（cfg.js 配内容，render.mjs 逐帧出图；06 AI 产品图在用） |
| 4 | 极简杂志 | m | 仅静态样式 |
| 5 | 知识黑框（三段式） | k | 仅静态样式 |
| 6 | 逐字大字幕 | h | 仅静态样式 |
| 7 | 电影宽银幕 | c | 仅静态样式 |
| 8 | 手账便利贴 | j | 仅静态样式；字体 ZCOOL KuaiLe / Ma Shan Zheng（google/fonts 仓库 ofl/） |
| 9 | AI 终端 | a | 仅静态样式；字体 JetBrains Mono |

| 10 | 播客访谈 | p | 仅静态样式 |
| 11 | 综艺花字 | v | 仅静态样式；字体 ZCOOL KuaiLe |
| 12 | 商务清单 | b | 仅静态样式 |
| 13 | 通知气泡 | q | 仅静态样式 |
| 14 | 复古录像带 | r | 仅静态样式 |
| 15 | 瑞士海报 | w | 仅静态样式 |
| 16 | 发布会 | kn | 仅静态样式 |
| 17 | 报纸头条 | np | 仅静态样式 |
| 18 | 漫画分镜 | cm | 仅静态样式 |
| 19 | 霓虹夜色 | ne | 仅静态样式 |
| 20 | 黑板粉笔 | ch | 仅静态样式 |
| 21 | 游戏任务 | gm | 仅静态样式 |
| 22 | 国风水墨 | gf | 仅静态样式 |
| 23 | 杂志封面 | mg | 仅静态样式 |
| 24 | 全息科技 | ho | 仅静态样式 |
| 25 | 拍立得 | pl | 仅静态样式 |
| 26 | 购物小票 | rc | 仅静态样式 |
| 27 | 地铁导视 | mt2 | 仅静态样式 |
| 28 | 复古电脑 | os | 仅静态样式 |
| 29 | 快递面单 | sh | 仅静态样式 |
| 30 | 任务看板 | kb | 仅静态样式 |
| 31 | 警示胶带 | wt | 仅静态样式 |
| 32 | 时间轴 | tl | 仅静态样式 |
| 33 | 日历撕页 | cal | 仅静态样式 |
| 34 | 片头字幕 | cr | 仅静态样式 |
| 35 | Y2K 千禧 | y2 | 仅静态样式 |
| 36 | 黑金奢华（高端） | lx | 仅静态样式 |
| 37 | 画廊展签（高端） | gl | 仅静态样式 |
| 38 | 时装大片（高端） | vg | 仅静态样式 |
| 39 | 财经深蓝（高端） | fn | 仅静态样式 |
| 40 | 极光玻璃（高端） | au | 仅静态样式 |
| 41 | 对称美学（高端） | wa | 仅静态样式 |
| 42 | 演讲舞台（高端） | sp | templates/stage/stage_tpl.html（动画版，render05s.mjs） |
| 43 | 香槟邀请函（高端） | iv | 仅静态样式 |
| 44 | 口碑墙 · 倾斜滚墙 | tw-a | templates/testimonial-wall/wall.html（独立动效片段，8 秒） |
| 45 | 口碑墙 · 星环隧道 | tw-b | templates/testimonial-wall/vortex.html（独立动效片段，8.5 秒） |
| 46 | 口碑墙 · 消息轰炸 | tw-c | templates/testimonial-wall/notify.html（独立动效片段，8.5 秒） |
| 47 | 发布会「一根线」 | kn2 | templates/keynote/keynote.html（全片黑白灰只有一根青柠绣线：走针开场 / 大字 / 微距缎面绣名字 / 卡点换产品 / 数字 / 全家福 / 结尾，约 20–25 秒） |
| 48 | 多彩动感（Etsy-Tony 日更） | cp | templates/color-pop/episode.html（每屏换色 + 贴纸拍上镜头震动 + 关键词逐字弹 + 手绘圈 + 五色条带转场，样片 27 秒） |
| 49 | 发布会 · 深空光晕 | cg | templates/cinema/glow.html（黑底流动光晕 + 毛玻璃 + 逐字模糊显现，带实拍素材窗；叠素材流程见 cinema/README.md） |
| 50 | 发布会 · 钛金影院 | ct | templates/cinema/titan.html（电影黑边 + 金属流光字 + 镜头光晕 + 3D 手机 + 宽银幕素材条） |
| 51 | 发布会 · 白昼极简 | cd | templates/cinema/day.html（浅灰白 + 品牌蓝 + 前景虚化光斑 + 圆角视频框） |
| 52 | 知识讲解 · 纪录片式 | ex | templates/explainer/explainer.html（实拍铺满全屏 + 政策原文纸片/荧光笔/手绘批注/贴纸标签，连续镜头不翻页，整条透明层叠在素材上） |
| 53 | 知识讲解 · 收据拆账 | ex-fee | templates/explainer/fees.html（收据打印 + 推近费用行 + 批注 + 盖章 + 警示胶带） |
| 54 | 知识讲解 · 镂空大字横移 | ex-star | templates/explainer/star.html（大数字镂空透出实拍 + 指标横移长镜头 + 圆环计数 + 徽章） |
| 55 | 知识讲解 · 手机实录 | ex-app | templates/explainer/ads.html（3D 手机界面示意 + 逐行圈重点 + 手指点开关 + 规则对比） |
| 51b | 白昼极简 · 网站功能宣传版 | cd-promo | templates/promo-day/promo.html（每日 09:23 网站宣传用：实拍钩子 + 圆角框录屏 + 结尾网址和评论关键词；每期只写配置文件） |
| 56 | Etsy 政策速递 · Shopwright 暖白青柠 | pb | video-drop templates/policy-brief/（engine.js + episodes/epNNN.js；check.py 自检、sfx.py 音效；选题台账 topics.md） |
| 57 | AI浪潮 · 钴蓝荧光黄 | aw | templates/ai-wave/episode.html（每日 AI 新闻；Gemini 交付表格 → 出片） |
| 58 | 移轴微缩 · 玩具城市沙盘 | tm | video-drop templates/etsytony-miniature/（Three.js 沙盘 + 合成音效，每期一份节拍表） |
| 59 | 科普治愈 · 纸光 | sh2 | video-drop templates/science-healing/（自然现象 → 人生道理） |
| 60 | TonyBook 极简杂志（4 号动态版） | mag | video-drop templates/tonybook-mag/（细线刊头、衬线标题、实拍素材，ElevenLabs Will） |
| 61 | 网站功能分屏 A（旧，2026-11-06 起由 51b 替换） | fs | templates/feature-split/board.html（上半屏面板 + 手机录屏） |
| 62 | TonyBook 助理聊天（2026-10-31 起停用） | tc | video-drop templates/tonybook-chat/ |
| 63 | 新闻快讯台 · 国际新闻台 breaking news 风格（深蓝演播室 + 新闻红 + 白色标题条；政策速递新外观，2026-11-10 样片，待 Tony 定是否替换 56 号） | pd | video-drop templates/policy-desk/（和 56 号读同一种 episodes/epNNN.js，多一种 quote 原文纸条场景；开场 BREAKING NEWS 突发大字 + 实拍素材通栏 1080×608 + 两层字幕条 + 底部滚动条 + 红白斜条转场；OUR TAKE 场景自动出「ANALYSIS · 我们的看法」标签；英文字体 Barlow Condensed 在模板 fonts/ 里） |

### 64–79 创作者风格包（2026-11-18，templates/creator-pack/，一个 pack.html 全包）

| 号 | 名称 | 代号 | 动画版实现 |
|---|---|---|---|
| 64 | 大字砸屏 Bold Type | bt | templates/creator-pack/pack.html?tpl=bt（纯字，每拍换底色，大字砸屏 + 震屏） |
| 65 | 贴纸拼贴 | sk | templates/creator-pack/pack.html?tpl=sk（牛皮纸 + 拍立得实拍框 + 剪报字 + 模切贴纸） |
| 66 | 漫画演绎 | ct | templates/creator-pack/pack.html?tpl=ct（漫画格（Codex 漫画场景图）+ 右上画中画 + BLOCKED 大字） |
| 67 | 杂志大片 Editorial | ed | templates/creator-pack/pack.html?tpl=ed（全屏实拍 + 衬线刊头/引语） |
| 68 | 产品演示 | pd | templates/creator-pack/pack.html?tpl=pd（蓝底网站窗口打字/点击 + 左下圆形人像） |
| 69 | 梗图反应 | mm | templates/creator-pack/pack.html?tpl=mm（上半屏梗图卡 + 下半屏实拍推镜头/定格） |
| 70 | 动态图解 | mg | templates/creator-pack/pack.html?tpl=mg（上半屏信息图（进度条/迷雾/路线）+ 下半屏实拍） |
| 71 | 白板手绘 | wb | templates/creator-pack/pack.html?tpl=wb（上半屏逐笔手绘 + 下半屏实拍） |
| 72 | 生活 Vlog | vl | templates/creator-pack/pack.html?tpl=vl（全屏 B-roll + 手写标题） |
| 73 | 回复评论 | rp | templates/creator-pack/pack.html?tpl=rp（评论卡 + 圆角实拍 + 编号要点） |
| 74 | 照片堆叠 | ps | templates/creator-pack/pack.html?tpl=ps（照片甩到桌上，最后一张是实拍） |
| 75 | 榜单倒数 | cd | templates/creator-pack/pack.html?tpl=cd（进度格 + 橙色大编号 + 上下两路实拍） |
| 76 | 胶片手绘质感 | dt | templates/creator-pack/pack.html?tpl=dt（录像带 OSD + 颗粒 + 抖动手绘圈 + 黄色大字） |
| 77 | 播客切片 | pc | templates/creator-pack/pack.html?tpl=pc（双人上下窗 + 说话人高亮 + 声波） |
| 78 | 新闻评论 | nc | templates/creator-pack/pack.html?tpl=nc（原文卡荧光笔 + 「我的看法」角标） |
| 79 | 4:3 横版口播 | wd | templates/creator-pack/pack.html?tpl=wd（1440×1080，抖音里居中显示、界面落在黑边不挡画面；章节标签 + 要点卡） |

**抖音遮挡安全区（64 号起所有竖版模板都按这个排）**：顶部 0–200、底部 1460 以下（账号名/文案/评论框）、右侧 930 以右 860–1600（按钮列）会被抖音界面盖住，字幕、重点字、人脸不放进去；`render.py guide` 叠遮挡区检查。详见 templates/creator-pack/README.md。

以后新模板接着编 80 号，加到这张表和样张页。

高端系列另用字体：Cormorant Garamond、Playfair Display、Cinzel、Bodoni Moda、Jost（同样来自 google/fonts ofl/）。

注意：模板内部不要用 class="t"（它是模板容器的类名，默认隐藏）。

字体：ZCOOL KuaiLe、Ma Shan Zheng、Long Cang、JetBrains Mono 来自 google/fonts 仓库 ofl/（git sparse-checkout 后装进 ~/.fonts）。

做动画版：照 docu_tpl.html 的结构（window.render(t) 逐帧驱动、CFG 配置），把对应代号的 CSS 搬过去。
