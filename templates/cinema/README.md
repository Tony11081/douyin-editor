# 49–51 · 发布会电影感（Etsy-Tony 日更，带实拍素材）

三个方向共用 `core.js`（时间轴、缓动、逐字模糊显现、打字、素材窗挖洞、字幕、转场），每期改 `window.EP` / `window.TL` 和各屏文字。

| 号 | 文件 | 风格 | 素材窗 `WIN` |
|---|---|---|---|
| 49 | glow.html 深空光晕 | 纯黑 + 一团流动光晕（唯一颜色）+ 毛玻璃卡 + 逐字从模糊变清晰 | 发光圆角玻璃窗 x60 y560 960×540 |
| 50 | titan.html 钛金影院 | 石墨底 + 电影黑边 + 金属流光字 + 镜头光晕 + 3D 手机 + 时间码 | 宽银幕条：素材铺 x0 y640 1080×608，只露中间 2.39:1 |
| 51 | day.html 白昼极简 | 苹果官网浅灰白 + 唯一品牌蓝 + 前景虚化光斑 + 悬浮白卡 | 圆角视频框 x80 y560 920×518 |

## 叠实拍素材（每期都要加，做到不违和）

素材从模板「下面」露出来，模板自己的暗角、颗粒、标签、文字盖在素材上面，所以看着是一体的。

1. `python3 -I render.py video glow.html base.mp4` 出整条画面（素材窗是空的）。
2. `python3 -I render.py hole glow.html hole.webm 3.6 7.8` 出素材场景那段的透明层（素材窗挖空，带圆角/暗角/标签）。时间按 `TL` 里素材场景的起止。
3. 两个文件放进 video-drop 仓库，用提交 SHA 的 raw 链接 import。
4. 剪辑服务器 render：base 作 video_id，`clips:[{start:0,end:时长}]`，captions none，effects 全关；overlays 按顺序写两条：
   - 素材：`{video_id, start:场景开始, from, duration:场景时长, x,y,w,h: WIN, layer:"front"}`
   - 透明层：`{url: hole.webm, start:场景开始, duration:场景时长, x:0,y:0,w:1080,h:1920, layer:"front"}`
5. 配音、音乐用 mux 加（配音 1.3 倍，只加速配音）。

**素材只用 Mixkit 横屏、而且详情页写「Mixkit Stock Video Free License」的**；写「720p Version for Personal Use only / Restricted License」的不能商用（例：17450 深夜笔记本、39500 木匠凿子都是受限的）。核对方法见 etsy-policy-brief-video 技能第 6 步（record_web 录详情页看下载框）。已核对可商用：242 笔记本打字俯拍、772 木工车床特写、771 木匠工作室、206 咖啡馆笔记本。
