"""网站录屏：用 Playwright（Chromium）按脚本打开网页、点击、滚动、输入，录成 1080×1920 竖屏视频
并导入视频库。录好的片段在 render 的 clips 里按 video_id 和口播穿插，就是「功能演示」类视频。

steps 里每一步是一个对象（按顺序执行）：
  {"goto": "https://..."}                    打开网址
  {"click": "免费工具"}                       点击：写页面上的文字，或 Playwright 选择器（#id、.class、text=、css=）
  {"tap": [x, y]}                            按视口坐标点击（CSS 像素，手机布局宽 540 高 960）
  {"type": "ceramic mug", "into": "input[name=title]", "delay": 60}   逐字输入（delay 每字毫秒）
  {"fill": "...", "into": 选择器}            直接填入
  {"press": "Enter"}                         按键
  {"scroll": 700, "duration": 1.2}           平滑滚动（像素，负数向上；duration 秒，默认按距离）
  {"hover": 选择器}                          把手指移到元素上
  {"highlight": 选择器, "duration": 1.5}     用黄框圈出元素（讲解重点用）
  {"wait": 1.5}                              停留
  {"wait_for": 选择器}                       等元素出现
  {"cursor": false}                          隐藏/显示手指（true/false）
每一步之后都会停 settle 秒。结果里 marks 是每一步在成片里的秒数，用来对口播切镜头。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import editor
from editor import EditorError

_lock = threading.Lock()  # Chromium 比较吃内存，一次只录一个
W, H = 1080, 1920
LAYOUTS = {
    # 手机布局：CSS 视口 540×960、2 倍像素 → 录出来正好 1080×1920
    "mobile": {"viewport": {"width": 540, "height": 960}, "device_scale_factor": 2.0,
               "is_mobile": True, "has_touch": True,
               "user_agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                              "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")},
    # 电脑布局（窄高）：直接 1080 CSS 像素宽
    "desktop": {"viewport": {"width": W, "height": H}, "device_scale_factor": 1.0,
                "is_mobile": False, "has_touch": False,
                "user_agent": editor.UA},
}

# 假手指、点击涟漪、黄色高亮框、平滑滚动；用 add_init_script 注入，页面跳转后仍然有效
_INJECT = r"""
(() => {
  if (window.__dyrec) return;
  window.__dyrec = true;
  const css = `
  #__dy_cursor{position:fixed;left:0;top:0;width:46px;height:46px;margin:-23px 0 0 -23px;border-radius:50%;
    background:rgba(255,72,72,.5);border:3px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.35);
    pointer-events:none;z-index:2147483647;opacity:0;
    transition:transform .45s cubic-bezier(.2,.8,.2,1),opacity .25s;transform:translate(-200px,-200px)}
  .__dy_ripple{position:fixed;left:0;top:0;width:46px;height:46px;margin:-23px 0 0 -23px;border-radius:50%;
    border:3px solid rgba(255,72,72,.95);pointer-events:none;z-index:2147483646;
    animation:__dyr .55s ease-out forwards}
  @keyframes __dyr{from{transform:scale(.6);opacity:1}to{transform:scale(2.6);opacity:0}}
  .__dy_hl{position:fixed;border:4px solid #FFD400;border-radius:14px;
    box-shadow:0 0 0 4px rgba(0,0,0,.25),0 0 24px rgba(255,212,0,.8);pointer-events:none;
    z-index:2147483645;animation:__dyh .35s ease-out}
  @keyframes __dyh{from{transform:scale(1.15);opacity:0}to{transform:scale(1);opacity:1}}`;
  const add = () => {
    if (document.getElementById('__dy_cursor')) return;
    const st = document.createElement('style'); st.textContent = css;
    (document.head || document.documentElement).appendChild(st);
    const c = document.createElement('div'); c.id = '__dy_cursor';
    document.documentElement.appendChild(c);
  };
  if (document.readyState !== 'loading') add(); else document.addEventListener('DOMContentLoaded', add);
  window.__dyMove = (x, y, show) => { add(); const c = document.getElementById('__dy_cursor');
    c.style.transform = `translate(${x}px,${y}px)`; c.style.opacity = show ? 1 : 0; };
  window.__dyTap = (x, y) => { add();
    const r = document.createElement('div'); r.className = '__dy_ripple';
    r.style.left = x + 'px'; r.style.top = y + 'px';
    document.documentElement.appendChild(r); setTimeout(() => r.remove(), 650);
    const c = document.getElementById('__dy_cursor');
    c.style.transition = 'transform .1s'; c.style.transform = `translate(${x}px,${y}px) scale(.75)`;
    setTimeout(() => { c.style.transform = `translate(${x}px,${y}px)`;
      c.style.transition = 'transform .45s cubic-bezier(.2,.8,.2,1),opacity .25s'; }, 110); };
  window.__dyHighlight = (x, y, w, h, ms) => { add();
    const d = document.createElement('div'); d.className = '__dy_hl';
    d.style.left = (x - 8) + 'px'; d.style.top = (y - 8) + 'px';
    d.style.width = (w + 16) + 'px'; d.style.height = (h + 16) + 'px';
    document.documentElement.appendChild(d); setTimeout(() => d.remove(), ms); };
  window.__dyScroll = (dy, ms) => new Promise(res => {
    const y0 = window.scrollY, t0 = performance.now();
    const ease = t => t < .5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    const f = now => { const p = Math.min(1, (now - t0) / ms); window.scrollTo(0, y0 + dy * ease(p));
      if (p < 1) requestAnimationFrame(f); else res(); };
    requestAnimationFrame(f); });
})();
"""

_SELECTOR_RE = re.compile(r"^(text=|css=|xpath=|role=|id=|#|\.|\[|//|\*|[a-zA-Z][\w-]*[.#\[:>])")


def _is_selector(s: str) -> bool:
    return bool(_SELECTOR_RE.match(s)) or " > " in s


def _by_text(page, s: str):
    """页面文字 → 优先找可见的链接/按钮，再退回任意文字。"""
    for role in ("link", "button", "tab", "menuitem"):
        loc = page.get_by_role(role, name=s).filter(visible=True)
        if loc.count():
            return loc.first
    loc = page.get_by_text(s, exact=False).filter(visible=True)
    if loc.count():
        return loc.first
    return page.get_by_text(s, exact=False).first


def _visible_texts(page) -> list[str]:
    """出错时列出页面上可点的文字，方便改脚本。"""
    try:
        return page.evaluate("""() => {
          const out = [];
          for (const el of document.querySelectorAll('a,button,[role=button],input[type=submit]')) {
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) continue;
            const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ');
            if (t && !out.includes(t)) out.push(t.slice(0, 40));
            if (out.length >= 60) break;
          }
          return out; }""")
    except Exception:
        return []


def _resolve(page, target: Any):
    if isinstance(target, dict):  # {"role": "button", "name": "提交"} / {"placeholder": "..."} / {"label": "..."}
        if "role" in target:
            return page.get_by_role(target["role"], name=target.get("name")).first
        if "placeholder" in target:
            return page.get_by_placeholder(target["placeholder"]).first
        if "label" in target:
            return page.get_by_label(target["label"]).first
        if "text" in target:
            return page.get_by_text(target["text"], exact=bool(target.get("exact"))).first
        raise EditorError(f"不认识的目标写法 {target}")
    s = str(target).strip()
    if not s:
        raise EditorError("目标不能为空")
    if _is_selector(s):
        return page.locator(s).first
    return _by_text(page, s)


def _center(loc, page) -> tuple[float, float]:
    loc.scroll_into_view_if_needed(timeout=8000)
    box = loc.bounding_box()
    if not box:
        raise EditorError("元素不可见，拿不到位置")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def record(url: str, steps: list[dict] | None, name: str | None = None, layout: str = "mobile",
           settle: float = 0.8, cursor: bool = True, progress=lambda m: None) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError as e:
        raise EditorError("服务器没装 playwright，请 update_server 重新安装") from e
    if layout not in LAYOUTS:
        raise EditorError(f"layout 只能是 {' / '.join(LAYOUTS)}")
    if not re.match(r"^https?://", url or ""):
        raise EditorError("url 要以 http:// 或 https:// 开头")
    steps = steps or []
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or not st:
            raise EditorError(f"steps[{i}] 应该是对象，例如 {{\"click\": \"免费工具\"}}")
    settle = max(0.0, float(settle))

    vid = uuid.uuid4().hex[:12]
    d = editor.VIDEOS / vid
    d.mkdir(parents=True)
    rec_dir = d / ".rec"
    marks: list[dict[str, Any]] = []
    t0 = 0.0
    show = bool(cursor)

    def mark(i: int, action: str, detail: str = "") -> None:
        marks.append({"step": i, "action": action, "detail": detail[:60], "t": round(time.time() - t0, 2)})

    with _lock:
        try:
            progress("启动浏览器")
            with sync_playwright() as p:
                # 录像帧的尺寸跟浏览器窗口的真实像素走：手机布局要 2 倍像素才能录出清晰的 1080×1920
                dsf = LAYOUTS[layout]["device_scale_factor"]
                browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--lang=zh-CN",
                                                  "--font-render-hinting=none", "--hide-scrollbars",
                                                  f"--force-device-scale-factor={dsf:g}"])
                ctx = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai",
                                          record_video_dir=str(rec_dir), record_video_size={"width": W, "height": H},
                                          color_scheme="light", **LAYOUTS[layout])
                ctx.set_default_timeout(12000)
                ctx.add_init_script(_INJECT)
                t0 = time.time()
                page = ctx.new_page()
                try:
                    progress(f"打开 {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except PWTimeout:
                        pass
                    time.sleep(max(0.6, settle))
                    t_ready = time.time() - t0
                    mark(-1, "ready", url)
                    for i, st in enumerate(steps):
                        progress(f"第 {i + 1}/{len(steps)} 步 {json.dumps(st, ensure_ascii=False)[:50]}")
                        try:
                            _do_step(page, st, settle, show, mark, i)
                        except EditorError:
                            raise
                        except PWTimeout as e:
                            texts = _visible_texts(page)
                            raise EditorError(
                                f"第 {i + 1} 步 {json.dumps(st, ensure_ascii=False)} 找不到目标或超时：{str(e).splitlines()[0][:200]}\n"
                                f"当前页面 {page.url}\n页面上可点的文字：{' | '.join(texts[:40])}") from e
                        if "cursor" in st:
                            show = bool(st["cursor"])
                    time.sleep(max(0.5, settle))
                    mark(len(steps), "end")
                finally:
                    video = page.video
                    page.close()
                    ctx.close()
                    browser.close()
                    webm = Path(video.path()) if video else None
            if not webm or not webm.exists():
                raise EditorError("没有录到视频")
            progress("转码")
            trim = max(0.0, t_ready - 0.25)
            src = d / "source.mp4"
            editor.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{trim:.3f}", "-i", str(webm),
                        "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1,fps=30", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(src)])
            shutil.rmtree(rec_dir, ignore_errors=True)
            info = editor.probe(src)
            _check_filled(src)
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
    for m in marks:
        m["t"] = round(max(0.0, m["t"] - trim), 2)
    meta = {"video_id": vid, "name": name or f"录屏·{re.sub(r'^https?://', '', url)[:30]}", "url": "",
            "source": src.name, **info,
            "recorded": {"url": url, "layout": layout, "steps": steps, "marks": marks}}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return {k: meta[k] for k in ("video_id", "name", "duration", "width", "height")} | {"marks": marks}


def _check_filled(src: Path) -> None:
    """录像没铺满（右下角是录像器补的灰色）说明浏览器像素倍率没生效，直接报错而不是交出半幅画面。"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.3", "-i", str(src), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120).stdout
    if len(raw) < W * H * 3:
        return
    gray = 0
    for x, y in ((W - 6, H - 6), (W // 2, H - 6), (W - 6, H // 2), (W - 6, 6)):
        px = raw[(y * W + x) * 3:(y * W + x) * 3 + 3]
        if all(118 <= c <= 138 for c in px):
            gray += 1
    if gray >= 3:
        raise EditorError("录像只占了画面一角（其余是灰色），浏览器像素倍率没生效；请 update_server 后再试")


def _do_step(page, st: dict, settle: float, show: bool, mark, i: int) -> None:
    def move(x: float, y: float) -> None:
        page.evaluate("([x,y,s]) => window.__dyMove(x,y,s)", [x, y, show])

    def tap(x: float, y: float) -> None:
        if show:
            page.evaluate("([x,y]) => window.__dyTap(x,y)", [x, y])

    if "goto" in st:
        page.goto(str(st["goto"]), wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        mark(i, "goto", str(st["goto"]))
    elif "click" in st:
        loc = _resolve(page, st["click"])
        loc.wait_for(state="visible", timeout=12000)
        x, y = _center(loc, page)
        move(x, y)
        time.sleep(0.5 if show else 0.1)
        tap(x, y)
        time.sleep(0.18)
        mark(i, "click", str(st["click"]))
        loc.click(timeout=10000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=6000)
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
    elif "tap" in st:
        x, y = float(st["tap"][0]), float(st["tap"][1])
        move(x, y)
        time.sleep(0.5 if show else 0.1)
        tap(x, y)
        time.sleep(0.18)
        mark(i, "tap", f"{x:.0f},{y:.0f}")
        page.mouse.click(x, y)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
    elif "type" in st or "fill" in st:
        if "into" not in st:
            raise EditorError(f"第 {i + 1} 步缺少 into（输入到哪个输入框）")
        loc = _resolve(page, st["into"])
        loc.wait_for(state="visible", timeout=12000)
        x, y = _center(loc, page)
        move(x, y)
        time.sleep(0.4 if show else 0.1)
        tap(x, y)
        loc.click(timeout=10000)
        mark(i, "type" if "type" in st else "fill", str(st.get("type", st.get("fill")))[:30])
        if "type" in st:
            loc.press_sequentially(str(st["type"]), delay=int(st.get("delay", 55)))
        else:
            loc.fill(str(st["fill"]))
    elif "press" in st:
        mark(i, "press", str(st["press"]))
        page.keyboard.press(str(st["press"]))
    elif "scroll" in st:
        dy = float(st["scroll"])
        ms = int(float(st.get("duration", min(2.2, 0.45 + abs(dy) / 900))) * 1000)
        mark(i, "scroll", f"{dy:.0f}")
        page.evaluate("([dy,ms]) => window.__dyScroll(dy,ms)", [dy, ms])
    elif "hover" in st:
        loc = _resolve(page, st["hover"])
        loc.wait_for(state="visible", timeout=12000)
        x, y = _center(loc, page)
        move(x, y)
        mark(i, "hover", str(st["hover"]))
        try:
            loc.hover(timeout=5000)
        except Exception:
            pass
    elif "highlight" in st:
        loc = _resolve(page, st["highlight"])
        loc.wait_for(state="visible", timeout=12000)
        loc.scroll_into_view_if_needed(timeout=8000)
        box = loc.bounding_box()
        if not box:
            raise EditorError(f"第 {i + 1} 步 highlight 的元素不可见")
        dur = float(st.get("duration", 1.5))
        mark(i, "highlight", str(st["highlight"]))
        page.evaluate("([x,y,w,h,ms]) => window.__dyHighlight(x,y,w,h,ms)",
                      [box["x"], box["y"], box["width"], box["height"], int(dur * 1000)])
        time.sleep(dur)
    elif "wait_for" in st:
        _resolve(page, st["wait_for"]).wait_for(state="visible", timeout=int(float(st.get("timeout", 15)) * 1000))
        mark(i, "wait_for", str(st["wait_for"]))
    elif "wait" in st:
        mark(i, "wait", str(st["wait"]))
        time.sleep(max(0.0, float(st["wait"])))
    elif "cursor" in st:
        page.evaluate("(s) => window.__dyMove(-200,-200,s)", bool(st["cursor"]))
        mark(i, "cursor", str(st["cursor"]))
    else:
        raise EditorError(f"第 {i + 1} 步不认识：{json.dumps(st, ensure_ascii=False)}；"
                          "可用：goto / click / tap / type / fill / press / scroll / hover / highlight / wait / wait_for / cursor")
    if "wait" not in st and "cursor" not in st:
        time.sleep(settle)
