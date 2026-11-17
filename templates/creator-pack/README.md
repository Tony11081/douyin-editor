# 64–79 · 创作者风格包（2026-11-18）

Tony 2026-11-18 发的一组海外创作者剪辑风格截图（Bold type / Sticker collage / Cartoon / Editorial / Product demo / Memes / Motion graphics / Whiteboard / Vlog / Reply to a comment / 照片堆叠 / 榜单倒数 / Drawn texture / Podcast / News commentary），照着做成 15 个竖版动画模板；外加他同晚发的抖音 4:3 横版口播（画面居中、上下黑边放抖音界面）做成 79 号。

全部在一个文件 `pack.html` 里，`?tpl=代号` 选模板。1080×1920 / 30fps（79 号 1440×1080）。

| 号 | 代号 | 名称 | 素材窗（slot） | 要点 |
|---|---|---|---|---|
| 64 | bt | 大字砸屏 Bold Type | 无（纯字） | 每拍换底色，大字一行行砸上来 + 镜头震 + 闪白 |
| 65 | sk | 贴纸拼贴 Sticker Collage | P 拍立得框 | 牛皮纸底、剪报字、胶带、模切贴纸拍上、纸条字幕 |
| 66 | ct | 漫画演绎 Cartoon | P 右上画中画 | 漫画格（`scene` 放 Codex 生成的漫画场景图）、禁止标志、BLOCKED 大字、黄底漫画字幕 |
| 67 | ed | 杂志大片 Editorial | W 全屏 | 衬线刊头 + 细线 + 期号，衬线引语（斜体金色强调），颗粒 |
| 68 | pd | 产品演示 Product Demo | P 左下圆形 | 蓝底、步骤胶囊、网站窗口打字 → 光标点按钮 → 进度条 |
| 69 | mm | 梗图反应 Memes & Reactions | P 下半屏 | 上半屏收据卡逐行打勾 + 标签；下半屏推镜头（zoom 1.35）+ 定格框 |
| 70 | mg | 动态图解 Motion Graphics | P 下半屏 | 信息量进度条、迷雾散开、路线画到星标 |
| 71 | wb | 白板手绘 Whiteboard | P 下半屏 | 冰山逐笔画出 + 笔尖跟随 + 手写标注 |
| 72 | vl | 生活 Vlog | W 全屏 | 手写标题 + 下划线、暖色、日期 |
| 73 | rp | 回复评论 Reply to a Comment | P 圆角窗 | 评论卡弹出 + 荧光笔划重点，下面编号要点逐条出 |
| 74 | ps | 照片堆叠 Photo Stack | L 最上面一张 | 照片一张张甩到桌上，最后一张是实拍 |
| 75 | cd | 榜单倒数 Countdown List | L 上 + P 下 | 进度格 1✓2✓3…、橙色大编号翻页 |
| 76 | dt | 胶片手绘质感 Drawn Texture | P 全屏 | 扫描线、颗粒、PLAY ▶ / SP、时间码、抖动手绘圈 + 黄色大字 |
| 77 | pc | 播客切片 Podcast Clip | T 上 + P 下 | ON AIR、说话人高亮框切换、声波、逐词字幕 |
| 78 | nc | 新闻评论 News Commentary | P 圆角窗 | 原文卡片 + 荧光笔、「我的看法」角标 |
| 79 | wd | 4:3 横版口播 Wide 4:3 | T 全屏（1440×1080） | 章节标签 + 进度（对应抖音「章节要点」）、姓名条、要点卡、底部字幕 |

## 抖音遮挡安全区（所有竖版模板都按这个排）

抖音全屏播放时会盖住：顶部 0–200（搜索/标签栏）；**底部 1460 以下**（账号名、文案、评论框）；**右侧 930 以右、860–1600**（头像/点赞/评论/收藏/分享）。
所以字幕、重点字、人脸都放在 y≤1460，右侧按钮列不放字。出片前用 `guide` 模式叠一层遮挡区检查：

```
python3 -I render.py guide rp 3,5.5        # guide_rp_*.png，红色区域就是会被挡住的地方
```

79 号 4:3 横版在抖音里居中显示，界面都落在上下黑边，画面不被挡；适合长口播（发布时按 `chapters` 打章节点）。

## 渲染

```
python3 -I render.py stills <代号> 1.5,4,6       # 检查图（素材窗用 sample/foot_*.jpg 垫底）
python3 -I render.py hole   <代号> out.webm      # 透明 webm（素材窗挖空），叠在实拍上
python3 -I render.py meta   <代号> > x.meta.json # 素材窗位置/时间（含推镜头），compose.py 用
LABEL=1 python3 -I render.py hole ...            # 顶部加「编号 · 名字」小标签（只给样片合集用）
```

改文案：`render.py stills|hole <代号> ... '<cfg JSON>'`，或页面 `?cfg=`。各模板认的键见 pack.html 里 `C('键', 默认值)`，常用：`caps`（字幕，`[词]` = 重点词，`t0/t1` 秒）、`dur`（时长）、每个模板自己的标题/列表键（如 bt 的 `beats`、rp 的 `question`/`list`、cd 的 `items`、wd 的 `chapters`/`chapter`/`point`）。

## 叠实拍出片（剪辑服务器）

1. 每段 `hole` 出透明 webm + `meta`，webm 推到本仓库，用提交 SHA 的 raw 链接。
2. 写 plan.json（素材槽 → 视频库 video_id 和原始宽高），`python3 -I compose.py plan.json > spec.json`。
3. 剪辑服务器 `render(spec)`：素材按 cover 铺进各窗（layer base），模板透明层盖在上面（layer front）。79 号 spec 里 width 1440、height 1080。
4. `mux` 加配音和音乐（配音按各方向规矩加速，只加速配音）。

## 样片

`samples/` 是 2026-11-18 的样片透明层（带编号标签）和 meta。样片素材：P = indo_cafe_laptop（374646221bc8）、W = 木工（f9c64a04ea1f）、L = mixkit-242（d363bf39d3b7）、T = indo_coworkers（c078af4b6e25）。
`sample/` 是本地预览用的截图和照片（照片堆叠、漫画格用的漫画化截图 `comic_team.jpg`）；正式出片时 66 号漫画场景、65 号贴纸按规矩交给服务器 Codex 生成。

字体（fonts/，均为 OFL，来自 google/fonts）：Anton、Playfair Display、Caveat、Long Cang、ZCOOL KuaiLe、VT323、Oswald。
