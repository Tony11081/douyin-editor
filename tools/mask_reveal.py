"""蒙版卡点模板（Cedar Shed 那种「黑白底片 → 按拍点一块块上色 → 全彩」）。

每个场景占 N 拍（默认 4）：第 0 拍切进来是冷调黑白，第 1、2 拍各亮一部分，第 3 拍全彩。
蒙版方式（reveal）：
  wipe     斜向擦除，从左到右分两步亮开
  hue      按颜色先亮：hues 写一或两组色相范围（OpenCV 0-180），第 1 拍亮第一组，第 2 拍加第二组
  luma     先亮最亮的地方（窗光、灯），再亮中间调
  stripes  横条一条条亮（半拍一条）
  radial   从画面中心向外圆形扩开
  scan     一道白光横扫，光扫过的地方变彩色
用法：python3 mask_reveal.py config.json
config: {"out": "out.mp4", "w": 1280, "h": 720, "fps": 30, "beats": [拍点秒数...],
         "scenes": [{"src": "a.mp4", "in": 2.0, "beats": 4, "reveal": "wipe", "hues": [[0,25]]}, ...],
         "audio": "music.mp3", "audio_start": 12.3}
beats 是音乐里的拍点（相对音乐开头）；第一个场景从 beats[0] 开始，成片的 0 秒对应音乐的 beats[0]。
"""
from __future__ import annotations

import json
import subprocess
import sys

import cv2
import numpy as np

EASE = 0.12  # 每次亮开用多少秒渐变


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def grade_bw(f: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    g = np.clip((g - 0.5) * 1.18 + 0.47, 0, 1)                        # 加对比、略压暗
    g = g * g * (3 - 2 * g) * 0.35 + g * 0.65                          # 轻 S 曲线
    bw = np.stack([g * 1.04, g * 1.0, g * 0.95], -1)                   # BGR：略偏冷
    return np.clip(bw, 0, 1)


def grade_color(f: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.18, 0, 255)                  # 彩色部分更饱和，和黑白反差更大
    c = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255
    return np.clip((c - 0.5) * 1.06 + 0.5, 0, 1)


def soft(m: np.ndarray, k: int = 31) -> np.ndarray:
    return cv2.GaussianBlur(m.astype(np.float32), (k, k), 0)


def stage_mask(kind: str, stage: int, p: float, f: np.ndarray, sc: dict, xx, yy, t_in: float, beat: float):
    """stage 1/2 的局部蒙版；p 是这一步的渐变进度 0-1。"""
    h, w = f.shape[:2]
    if kind == "wipe":
        edge = (0.40 if stage == 1 else 0.72) * p + (0.40 if stage == 2 else 0.0) * (1 - p)
        d = (xx / w) * 0.8 + (1 - yy / h) * 0.2
        return np.clip((edge - d) / 0.05 + 0.5, 0, 1)
    if kind == "hue":
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        groups = sc.get("hues") or [[0, 25]]

        def key(gs):
            m = np.zeros((h, w), np.float32)
            for lo, hi in gs:
                sel = (hsv[..., 0] >= lo) & (hsv[..., 0] <= hi) & (hsv[..., 1] > sc.get("min_sat", 60)) & (hsv[..., 2] > 40)
                m = np.maximum(m, sel.astype(np.float32))
            return soft(m, 21)
        first = key(groups[:1])
        if stage == 1:
            return first * p
        return np.maximum(first, key(groups[:2]) * p) if len(groups) > 1 else np.maximum(first, soft(
            np.clip((cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) / 255.0 - 0.6) / 0.1, 0, 1), 25) * p)
    if kind == "luma":
        v = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        thr = 0.72 if stage == 1 else 0.42
        return soft(np.clip((v - thr) / 0.08, 0, 1), 25) * (p if stage == 1 else 1.0)
    if kind == "stripes":
        n = 6
        lit = (t_in - beat) / (beat / 2)                                # 从第 1 拍起每半拍亮一条
        k = int(np.clip(lit, 0, n))
        band = np.floor(yy / h * n)
        order = np.array([2, 4, 1, 5, 0, 3])                            # 不按顺序亮，更有节奏感
        m = np.isin(band, order[:max(k, 1)]).astype(np.float32)
        return soft(m, 15)
    if kind == "radial":
        r = np.hypot(xx - w / 2, yy - h / 2) / np.hypot(w / 2, h / 2)
        rad = (0.32 if stage == 1 else 0.66) * p + (0.32 if stage == 2 else 0.0) * (1 - p)
        return np.clip((rad - r) / 0.06 + 0.5, 0, 1)
    if kind == "scan":
        pos = ((stage - 1) + p) / 2 * 1.15                              # 两拍扫完
        d = (xx / w) * 0.85 + (yy / h) * 0.15
        return np.clip((pos - d) / 0.04 + 0.5, 0, 1)
    return np.zeros((h, w), np.float32)


def glow(kind: str, stage: int, p: float, xx, yy, w, h) -> np.ndarray | None:
    """scan 的白光带：在亮开的边缘加一道光。"""
    if kind != "scan":
        return None
    pos = ((stage - 1) + p) / 2 * 1.15
    d = (xx / w) * 0.85 + (yy / h) * 0.15
    return np.exp(-((d - pos) / 0.025) ** 2) * 0.55


def load_clip(src: str, t_in: float, dur: float, w: int, h: int, fps: int) -> list[np.ndarray]:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t_in}", "-i", src, "-t", f"{dur + 0.2}",
           "-vf", f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw, np.uint8, w * h * 3, i * w * h * 3).reshape(h, w, 3) for i in range(n)]


def main(cfg_path: str) -> None:
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    w, h, fps = cfg.get("w", 1280), cfg.get("h", 720), cfg.get("fps", 30)
    beats = cfg["beats"]
    t0 = beats[0]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                            "-pix_fmt", "yuv420p", cfg["out"] + ".video.mp4"], stdin=subprocess.PIPE)
    bi = 0
    for si, sc in enumerate(cfg["scenes"]):
        nb = sc.get("beats", 4)
        bt = [beats[bi + k] - t0 for k in range(nb + 1)]                # 这个场景的拍点（成片时间）
        bi += nb
        start, end = bt[0], bt[-1]
        beat = (end - start) / nb
        frames = load_clip(sc["src"], sc.get("in", 0.0), end - start, w, h, fps)
        f0, f1 = round(start * fps), round(end * fps)
        for fi in range(f0, f1):
            t = fi / fps
            f = frames[min(fi - f0, len(frames) - 1)]
            z = 1.0 + 0.05 * (t - start) / (end - start)                # 慢推，模仿云台推近
            if fi - f0 < 4:
                z += 0.035 * (1 - (fi - f0) / 4)                        # 切进来时轻微冲一下
            M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, z)
            f = cv2.warpAffine(f, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            bw, col = grade_bw(f), grade_color(f)
            kind = sc.get("reveal", "wipe")
            if t < bt[1]:
                m, g = np.zeros((h, w), np.float32), None
            elif t < bt[2]:
                p = ease((t - bt[1]) / EASE)
                m, g = stage_mask(kind, 1, p, f, sc, xx, yy, t - start, beat), glow(kind, 1, ease((t - bt[1]) / beat), xx, yy, w, h)
            elif t < bt[3]:
                p = ease((t - bt[2]) / EASE)
                m, g = stage_mask(kind, 2, p, f, sc, xx, yy, t - start, beat), glow(kind, 2, ease((t - bt[2]) / beat), xx, yy, w, h)
            else:
                prev = stage_mask(kind, 2, 1.0, f, sc, xx, yy, bt[3] - start, beat)
                p = ease((t - bt[3]) / EASE)
                m, g = prev + (1 - prev) * p, None
            out = col * m[..., None] + bw * (1 - m[..., None])
            if g is not None:
                out = out + g[..., None]
            for b in bt[1:4]:                                           # 每个拍点亮一下
                if 0 <= t - b < 2 / fps:
                    out = out * 1.07
            enc.stdin.write((np.clip(out, 0, 1) * 255).astype(np.uint8).tobytes())
        print(f"scene {si + 1} {sc.get('reveal')} {start:.2f}-{end:.2f}s", flush=True)
    enc.stdin.close()
    enc.wait()
    dur = beats[bi] - t0
    a = cfg.get("audio")
    if a:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cfg["out"] + ".video.mp4",
                        "-ss", f"{cfg.get('audio_start', 0) + t0}", "-i", a, "-t", f"{dur}",
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-af", f"afade=t=out:st={max(dur - 0.6, 0)}:d=0.6", "-shortest", cfg["out"]], check=True)
    else:
        subprocess.run(["mv", cfg["out"] + ".video.mp4", cfg["out"]], check=True)
    print("done", cfg["out"], f"{dur:.2f}s")


if __name__ == "__main__":
    main(sys.argv[1])
