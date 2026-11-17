"""64–78 创作者风格包渲染（pack.html，?tpl=代号）。
python3 -I render.py stills <代号> 1.5,4,6          → still_<代号>_<秒>.png 检查图（素材窗用 sample/foot_*.jpg 垫底）
python3 -I render.py hole   <代号> out.webm         → 整段透明 webm（素材窗挖空），叠在实拍上
python3 -I render.py guide  <代号> 3,5.5             → guide_*.png：叠抖音界面遮挡区检查
python3 -I render.py meta   <代号>                  → 打印素材窗 JSON（compose.py 用它算 overlays）
可加第 4 个参数：cfg JSON（覆盖文案，见 README）
"""
import os, sys, json, subprocess, pathlib, urllib.parse
from playwright.sync_api import sync_playwright

here = pathlib.Path(__file__).parent
mode, tpl = sys.argv[1], sys.argv[2]
FPS = 30

def url(hole=False, cfg=None):
    q = {"tpl": tpl}
    if hole: q["hole"] = "1"
    if cfg: q["cfg"] = cfg
    return (here / "pack.html").as_uri() + "?" + urllib.parse.urlencode(q)

cfg = None
if mode in ("stills", "guide") and len(sys.argv) > 4: cfg = sys.argv[4]
if mode in ("hole", "meta") and len(sys.argv) > (4 if mode == "hole" else 3): cfg = sys.argv[4 if mode == "hole" else 3]

with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    pg.goto(url(mode == "hole", cfg) + ("&guide=1" if mode == "guide" else "") + ("&label=1" if os.environ.get("LABEL") else "")); pg.wait_for_timeout(1200)
    pg.evaluate("document.fonts.ready")
    w, h = pg.evaluate("SIZE")
    if (w, h) != (1080, 1920):
        pg.set_viewport_size({"width": w, "height": h}); pg.wait_for_timeout(200)
    if mode in ("stills", "guide"):
        for t in [float(x) for x in sys.argv[3].split(",")]:
            pg.evaluate(f"render({t})"); pg.wait_for_timeout(60)
            pg.screenshot(path=str(here / f"{'guide' if mode == 'guide' else 'still'}_{tpl}_{t:05.2f}.png"))
    elif mode == "meta":
        print(json.dumps(pg.evaluate("META()"), ensure_ascii=False))
    else:
        out = sys.argv[3]
        n = int(round(pg.evaluate("DUR") * FPS))
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
                               "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "5M", "-deadline", "realtime", "-cpu-used", "8",
                               "-auto-alt-ref", "0", out + ".part.webm"], stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate(f"render({i / FPS})")
            ff.stdin.write(pg.screenshot(type="png", omit_background=True))
        ff.stdin.close(); rc = ff.wait()
        if rc == 0: pathlib.Path(out + ".part.webm").rename(out)
        else: sys.exit(rc)
    b.close()
