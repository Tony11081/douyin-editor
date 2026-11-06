# 52 · 知识讲解 · 纪录片式（Etsy-Tony 政策知识点）

为了不像幻灯片：
1. 实拍素材铺满全屏当舞台（不是放在框里），模板整条渲染成透明层叠在素材上，暗角/调色/颗粒统一质感。
2. 一个连续镜头：元素从镜头外进来、镜头推进/穿过关键词去下一段，不做「换页」；整层有手持感微漂移。
3. 信息做成「实物」：政策原文像纸片（荧光笔划重点 + 手绘箭头批注）、listing 标签像贴纸拍上来、但书用下三分之一线条。
4. 换素材镜头的地方用白闪盖住（TL.cut）。

出片：
1. 改 `TL`（各段起止、字幕）和各段文字；`python3 -I render.py stills explainer.html 2,6.4,12.4` 检查（预览底是棕色占位）。
2. `python3 -I render.py hole explainer.html overlay.webm 0 <总时长>` 出整条透明层，推到 video-drop，用提交 SHA 的 raw 链接。
3. 剪辑服务器 render：`video_id` = 第一段素材，`clips` 按顺序写每段素材（第二段起写自己的 video_id），总时长等于模板时长，换段时间点 = `TL.cut`；captions none、effects 全关；overlays 一条：透明层 `x0 y0 1080×1920 start 0 layer front`。
4. 配音和音乐用 mux（配音 1.3 倍）。

素材：横屏会被裁成竖屏中间那一条，选主体在画面正中的镜头，或者直接用竖屏素材；授权规则见 ../cinema/README.md。最好的素材是咱们车间自己拍的（激光切木牌、打包），手机竖拍 10 秒即可。
政策内容必须核对 Etsy 官方页面原文（本例出自 etsy.com/legal/creativity 的 Made by a seller 示例）。
