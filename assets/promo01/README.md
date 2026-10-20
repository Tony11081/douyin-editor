# 01 产品图代制作 · 动态图形层与原创配乐

- `overlay.html`：按时间逐帧绘制的动态图形（字幕、钩子、价格对比、前后对比、速度条、CTA），透明背景
- `render.mjs`：用 Chromium 逐帧截图（透明 PNG）
- `overlay01.webm`：VP9 带 alpha 的成品图形层（17.45s，1080×1920，30fps）
- `music.py` → `score.wav`：numpy 合成的原创配乐，124 BPM，节点与动画对齐（-16 LUFS）

时间轴对应 01 成片（render spec 的 clips 顺序不变时才对得上）。
