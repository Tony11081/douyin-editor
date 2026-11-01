"""47 号「发布会」：按 spec.json 渲染竖屏 1080×1920、30fps 的无声 mp4（或先出几张检查图）。

用法：
  python3 -I render.py video spec.json out.mp4
  python3 -I render.py stills spec.json 1.2,3.9,5.8   # 出检查图 still_<秒>.jpg 到当前目录
  python3 -I render.py plan spec.json                 # 只打印每页起止秒数（排配音用）
总时长 = 各页时长相加（每页可写 duration 覆盖默认值）。spec 字段见 README.md。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def load(spec_path: str) -> dict:
    p = Path(spec_path).resolve()
    spec = json.loads(p.read_text(encoding="utf-8"))
    for s in spec.get("scenes", []):  # 图片路径按 spec 所在目录解析
        if s.get("image") and not s["image"].startswith(("http", "file:", "data:")):
            s["image"] = (p.parent / s["image"]).resolve().as_uri()
    return spec


def open_page(p, spec: dict):
    exe = os.environ.get("CHROME_PATH")
    b = p.chromium.launch(args=["--no-sandbox", "--force-device-scale-factor=1", "--force-color-profile=srgb",
                                "--allow-file-access-from-files"], **({"executable_path": exe} if exe else {}))
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    pg.add_init_script(f"window.SPEC = {json.dumps(spec, ensure_ascii=False)};")
    pg.goto((HERE / "keynote.html").as_uri())
    pg.wait_for_function("typeof window.render === 'function'")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_load_state("load")
    pg.wait_for_timeout(300)
    return b, pg


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("video", "stills", "plan"):
        sys.exit(__doc__)
    spec = load(sys.argv[2])
    with sync_playwright() as p:
        b, pg = open_page(p, spec)
        total = pg.evaluate("window.TOTAL")
        if sys.argv[1] == "plan":
            for s in pg.evaluate("scenes.map(s => [s.type, s.t0, s.t0 + s.d])"):
                print(f"{s[0]:8s} {s[1]:6.2f} → {s[2]:6.2f}")
            print(f"总长 {total:.2f} 秒")
        elif sys.argv[1] == "stills":
            for t in [float(x) for x in sys.argv[3].split(",")]:
                pg.evaluate("t => window.render(t)", t)
                pg.screenshot(path=f"still_{t}.jpg", type="jpeg", quality=88)
        else:
            out, fps = sys.argv[3], 30
            tmp = str(Path(out).with_suffix(".part.mp4"))
            ff = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-maxrate", "10M", "-bufsize", "20M",
                 "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
                stdin=subprocess.PIPE)
            for i in range(int(round(total * fps))):
                pg.evaluate("t => window.render(t)", i / fps)
                ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
            ff.stdin.close()
            if ff.wait() != 0:
                sys.exit("ffmpeg 失败")
            os.replace(tmp, out)  # 编码成功才改成正式文件名
        b.close()


if __name__ == "__main__":
    main()
