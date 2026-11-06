# 51 号「白昼极简」· 网站功能宣传版（每日 09:23 那条线，2026-11-06 起替换「卡片式录屏」）

浅灰白底 + 唯一品牌蓝 + 前景虚化光斑。开头实拍素材铺满全屏、钩子大字压在素材上；每条干货上方蓝色小字（第一/第二/第三）+ 黑色大标题换句，网站录屏放在中间带柔和投影的圆角框里（框不动，录屏在里面滚）；结尾卡：网址 + 「评论区打 XX 两个字」。右上角常驻 Shopwright + openaigrowth.com。配音和音乐不变：Lan 女声 1.3 倍、mixkit_dreaming_big.mp3 0.07。

## 每期只写配置
复制 promo.cfg.js 为 cfg/epNNN.js，改：`dur` 成片时长；`hook`（t1 钩子结束秒、eye 小字、text 大字可用 <br>）；`segs`（每段 t0/t1/eye/title，标题一行 ≤ 11 个字）；`end`（t0、lead、kw 评论关键词、sub）；`subs`（按配音写，每句开始 = tts start + 0.3）。
检查：`CFG=cfg/epNNN.js python3 -I render.py stills promo.html 2,7,16,…`（预览里圆角框是空的，正常）。
透明层：`CFG=cfg/epNNN.js python3 -I render.py hole promo.html out.webm 0 <dur>` → 推到 video-drop（提交 SHA 的 raw 链接）。

## 合成（剪辑服务器 render）
- video_id = 钩子素材；clips：钩子素材 0–hook.t1，后面随便接够总长（会被挡住，只有圆角框和开头露出来）。
- overlays 按顺序：① 网站录屏（record_web mobile，cursor false，settle 0.3）`{video_id, start: hook.t1, from, duration: end.t0 - hook.t1, x 190, y 520, w 700, h 1244, layer front}`（框只露出录屏上面 860 高，页面要滚到关键内容）；② 透明层 `{url, start 0, duration dur, x0 y0 w1080 h1920, layer front}`。
- captions none，effects 全关，audio denoise/loudnorm 关。
- import 成片 → mux：voiceover {tts_id, at}，bgm mixkit_dreaming_big.mp3 音量 0.07，original_volume 0，loudnorm true，speed 1（配音 tts 时已 1.3 倍）。
