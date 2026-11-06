import sys, subprocess, pathlib
from playwright.sync_api import sync_playwright

here = pathlib.Path(__file__).parent
mode = sys.argv[1]  # "stills" or "video"
FPS = 30

with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    pg.goto((here / (sys.argv[4] if len(sys.argv) > 4 else "episode.html")).as_uri())
    pg.wait_for_timeout(800)
    if len(sys.argv) > 3 and sys.argv[3]:
        pg.evaluate(sys.argv[3])  # optional timeline override JS
    if mode == "stills":
        times = [float(x) for x in sys.argv[2].split(",")]
        for t in times:
            pg.evaluate(f"render({t})")
            pg.screenshot(path=str(here / f"still_{t:05.2f}.png"))
    else:
        out = sys.argv[2]
        dur = pg.evaluate("DUR")
        n = int(round(dur * FPS))
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
                               "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                               "-preset", "medium", "-crf", "18", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate(f"render({i / FPS})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
            if i % 300 == 0:
                print(f"frame {i}/{n}", flush=True)
        ff.stdin.close(); ff.wait()
    b.close()
