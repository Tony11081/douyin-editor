# 卡点视频工具

两个脚本配合着用：换素材 + 换音乐 + 换字 = 一条新视频。都在服务器上跑（`/opt/rea-video/.venv/bin/python`，自带 OpenCV / numpy / PIL）。

| 脚本 | 做什么 |
|---|---|
| `beat_pick.py` | 测整首歌的拍点，挑能量最强的一段，把拍点对准鼓点，写出 `beats.json` |
| `mask_reveal.py` | 蒙版卡点模板：每个场景黑白 → 局部上色 → 全彩，中英双语大字标题，品牌结尾卡 |

## 一条新视频的步骤

1. 素材：Mixkit 免费可商用空镜（`https://assets.mixkit.co/videos/<id>/<id>-720.mp4`），先用剪辑工具 `import_video` + `get_frames` 看画面再挑。
2. 音乐：Mixkit 曲库（`find_music`），用 rea-video 的 `analyze_audio` 挑 BPM 合适、鼓点强的。
3. 写 `config.json`（场景、蒙版方式、标题、结尾卡），`"beats_file": "beats.json"`。
4. `python beat_pick.py music.mp3 --config config.json` → `python mask_reveal.py config.json`
5. 交付：本机临时文件服务 → 剪辑工具 `import_video` → `mux`（original_volume=1）拿下载链接。

## config 示例

```json
{
  "out": "promo.mp4", "w": 1280, "h": 720, "fps": 30,
  "beats_file": "beats.json",
  "scenes": [
    {"src": "/opt/douyin-editor/data/videos/<video_id>/source.mp4", "in": 2.0, "beats": 4,
     "reveal": "hue", "hues": [[0, 10], [18, 35]],
     "title_en": "Laser Engraving", "title_zh": "激光雕刻 · 定制木牌"}
  ],
  "end_card": {"style": "big", "beats": 6, "label": "DESIGN · MAKE · SHIP", "brand": "Shopwright",
               "line": "Etsy 卖家的设计 · 生产 · 代发一站式", "url": "openaigrowth.com", "accent": [232, 119, 46]}
}
```

蒙版方式 `reveal`：`wipe` 斜擦、`hue` 按颜色先亮（`hues` 写 OpenCV 色相 0–180 的范围）、`luma` 亮处先亮、`stripes` 横条、`radial` 中心扩散、`scan` 白光横扫。
场景素材要稳（云台/三脚架），每场 4 拍；收尾场景 6 拍。字体：Playfair Display、Montserrat（Google Fonts，OFL）放在运行目录，中文用系统里的思源宋体。
