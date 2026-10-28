# 口播模板库（编号）

Tony 选模板只说编号。样张页：templates_page.html（已发布为 Claude 页面「Etsy-Tony 视频模板库」）。
gallery.html 是所有模板的静态样式（?tpl=<代号>&s=hook|card，背景放 bg/hook.jpg、bg/card.jpg）。

| 号 | 名称 | 代号 | 动画版实现 |
|---|---|---|---|
| 1 | 立体大字（背后抠像大字） | — | assets/promo23/overlay_tpl.html（behind + front 两层） |
| 2 | 纪录片 | d | templates/docu/docu_tpl.html（05 车上道歉在用） |
| 3 | 资讯快报 | n | 仅静态样式 |
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
| 42 | 演讲舞台（高端） | sp | 仅静态样式 |
| 43 | 香槟邀请函（高端） | iv | 仅静态样式 |

高端系列另用字体：Cormorant Garamond、Playfair Display、Cinzel、Bodoni Moda、Jost（同样来自 google/fonts ofl/）。

注意：模板内部不要用 class="t"（它是模板容器的类名，默认隐藏）。

字体：ZCOOL KuaiLe、Ma Shan Zheng、Long Cang、JetBrains Mono 来自 google/fonts 仓库 ofl/（git sparse-checkout 后装进 ~/.fonts）。

做动画版：照 docu_tpl.html 的结构（window.render(t) 逐帧驱动、CFG 配置），把对应代号的 CSS 搬过去。
