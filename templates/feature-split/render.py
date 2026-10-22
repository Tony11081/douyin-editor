"""把分屏模板的上半屏面板按时间轴渲染成带透明通道的 VP9 webm。

用法：python3 render.py timeline.json out.webm [--fps 15]
timeline.json：{"duration": 秒, "segments": [{"start","end","kind","n"?,"name"?,"note"?,"step"?}]}
  kind = open（开场卡）| feature（手机录屏段，n/name/note 是标签文字，step 是进度条第几格）| tip | end
成片里：录屏 overlays（layer: base，缩放到 w=716 h=912，x=182 y=224）在前，本面板（layer: base）在最后；
render 时 shift_y=700，caption_style {y: 0.672, size_ratio: 0.07, max_chars: 12}。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=15)
    a = ap.parse_args()
    tl = json.loads(Path(a.timeline).read_text())
    total = float(tl["duration"])
    n = int(round(total * a.fps))
    tmp = Path(tempfile.mkdtemp(prefix="board_"))
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--force-device-scale-factor=1"])
            pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            pg.add_init_script(f"window.TIMELINE = {json.dumps(tl['segments'], ensure_ascii=False)};")
            pg.goto((HERE / "board.html").as_uri())
            pg.wait_for_timeout(600)
            last = None
            for i in range(n):
                t = i / a.fps
                pg.evaluate("t => window.render(t)", t)
                f = tmp / f"f{i:05d}.png"
                state = pg.evaluate("""() => [...document.querySelectorAll('[style]')]
                                         .map(e => e.getAttribute('style')).join('|')""")
                if state == last and i:
                    shutil.copyfile(tmp / f"f{i - 1:05d}.png", f)  # 静止画面直接复用上一帧
                else:
                    pg.screenshot(path=str(f), omit_background=True)
                last = state
            b.close()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(tmp / "f%05d.png"),
                        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "28",
                        "-auto-alt-ref", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                        a.out], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
