"""发布会电影感模板渲染。
python3 -I render.py stills glow.html 1.5,5,9.5          → still_<秒>.png 检查图
python3 -I render.py video  glow.html out.mp4            → 整条画面（素材窗是黑的，等剪辑服务器叠素材）
python3 -I render.py hole   glow.html out.webm 3.6 7.8   → 素材场景那段的透明 webm（挖空素材窗，叠在素材上面）
"""
import sys, subprocess, pathlib, os
from playwright.sync_api import sync_playwright

here = pathlib.Path(__file__).parent
mode, page = sys.argv[1], sys.argv[2]
FPS = 30

with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    cfg = os.environ.get("CFG", "promo.cfg.js")  # 每期的配置文件
    url = (here / page).as_uri() + "?cfg=" + cfg + ("&hole=1" if mode == "hole" else "")
    pg.goto(url)
    pg.wait_for_timeout(1500)
    if mode == "stills":
        for t in [float(x) for x in sys.argv[3].split(",")]:
            pg.evaluate(f"render({t})")
            pg.screenshot(path=str(here / f"still_{t:05.2f}.png"))
    elif mode == "video":
        out = sys.argv[3]
        n = int(round(pg.evaluate("DUR") * FPS))
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "17", "-movflags", "+faststart", out],
                              stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate(f"render({i / FPS})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
        ff.stdin.close(); ff.wait()
    else:  # hole
        out, t0, t1 = sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
                               "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "6M", "-deadline", "realtime", "-cpu-used", "8",
                               "-auto-alt-ref", "0", out], stdin=subprocess.PIPE)
        i0, i1 = int(round(t0 * FPS)), int(round(t1 * FPS))
        for i in range(i0, i1):
            pg.evaluate(f"render({i / FPS})")
            ff.stdin.write(pg.screenshot(type="png", omit_background=True))
        ff.stdin.close(); ff.wait()
    b.close()
