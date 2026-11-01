"""口碑墙模板：按 spec.json 渲染竖屏 1080×1920、30fps 的无声 mp4（或先出几张检查图）。

用法：
  python3 -I render.py video spec.json out.mp4        # 整条（风格看 spec.style：wall | vortex）
  python3 -I render.py stills spec.json 1.2,3.9,5.8   # 出检查图 still_<秒>.jpg 到当前目录
spec 字段见 README.md；example.json 是示例（卡片内容是占位，正式发布前换成真实评价）。
没配音没音乐，加声音交给剪辑工具（mux / render 的 voiceover、bgm）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
STYLES = {"wall": ("wall.html", 8.0), "vortex": ("vortex.html", 8.5)}


def open_page(p, spec: dict):
    page_file, default_d = STYLES[spec.get("style", "vortex")]
    spec.setdefault("duration", default_d)
    if not spec.get("cards"):
        sys.exit("spec.cards 不能为空")
    args = ["--no-sandbox", "--force-device-scale-factor=1", "--force-color-profile=srgb"]
    exe = os.environ.get("CHROME_PATH")
    b = p.chromium.launch(args=args, **({"executable_path": exe} if exe else {}))
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    pg.add_init_script(f"window.SPEC = {json.dumps(spec, ensure_ascii=False)};")
    pg.goto((HERE / page_file).as_uri())
    pg.wait_for_function("typeof window.render === 'function'")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(300)
    return b, pg


def video(spec: dict, out: str, fps: int = 30) -> None:
    tmp = str(Path(out).with_suffix(".part.mp4"))
    with sync_playwright() as p:
        b, pg = open_page(p, spec)
        n = int(round(float(spec["duration"]) * fps))
        ff = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-maxrate", "10M", "-bufsize", "20M", "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
            stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate("t => window.render(t)", i / fps)
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
        b.close()
        ff.stdin.close()
        if ff.wait() != 0:
            sys.exit("ffmpeg 失败")
    os.replace(tmp, out)  # 编码成功才改成正式文件名，半截文件不会冒充成片


def stills(spec: dict, times: list[float]) -> None:
    with sync_playwright() as p:
        b, pg = open_page(p, spec)
        for t in times:
            pg.evaluate("t => window.render(t)", t)
            pg.screenshot(path=f"still_{t}.jpg", type="jpeg", quality=88)
        b.close()


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("video", "stills"):
        sys.exit(__doc__)
    spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if sys.argv[1] == "video":
        video(spec, sys.argv[3])
    else:
        stills(spec, [float(x) for x in sys.argv[3].split(",")])
