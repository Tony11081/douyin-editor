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

做动画版：照 docu_tpl.html 的结构（window.render(t) 逐帧驱动、CFG 配置），把对应代号的 CSS 搬过去。
