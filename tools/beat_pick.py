"""给卡点视频挑音乐片段、出拍点（配合 mask_reveal.py 用）。

做的事：
1. 用 rea-video 的音频分析测整首歌的拍点和 BPM
2. 在歌里找能量最强的一段（从小节头开始，长度 = 视频需要的拍数）
3. 在 ±半拍里微调相位，让拍点落在鼓点最强的位置（上次就是靠这一步把"切在两拍中间"修好的）
4. 写出 beats.json，mask_reveal.py 的 config 里写 "beats_file": "beats.json" 就能用

用法：
  python3 beat_pick.py music.mp3 --config config.json      # 按 config 里场景和结尾卡的拍数自动算要多少拍
  python3 beat_pick.py music.mp3 --beats 37 --start-beat 140   # 也可以手动指定
输出：beats.json（同目录），打印 BPM、选中的时间段和相位偏移。
需要：/opt/rea-video（rea-video 已装）、ffmpeg、numpy。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REA = __import__("os").environ.get("REA_DIR", "/opt/rea-video")


def to_wav(src: str) -> str:
    out = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", "22050", out], check=True)
    return out


def read_wav(path: str) -> tuple[np.ndarray, int]:
    w = wave.open(path)
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return x, w.getframerate()


def onset_flux(x: np.ndarray, sr: int, hop: int = 128) -> tuple[np.ndarray, np.ndarray]:
    n = (len(x) - 512) // hop
    fr = np.sqrt(np.mean(np.lib.stride_tricks.sliding_window_view(x, 512)[::hop][:n] ** 2, axis=1))
    flux = np.maximum(np.diff(fr), 0)
    # 第 j 个差分对应第 j+1 帧刚把起音包进来：时间按那一帧的结尾算，才对得上真实鼓点
    return flux, (np.arange(len(flux)) + 1) * hop / sr + 512 / sr


def beats_needed(cfg_path: str) -> int:
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    n = sum(s.get("beats", 4) for s in cfg["scenes"])
    if cfg.get("end_card"):
        n += cfg["end_card"].get("beats", 6)
    return n + 1                                                         # 最后一个场景的结束也要一个拍点


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("music")
    ap.add_argument("--config", help="mask_reveal 的 config，用来算要多少拍")
    ap.add_argument("--beats", type=int, help="要多少个拍点（场景拍数之和 + 1）")
    ap.add_argument("--start-beat", type=int, help="从第几拍开始；不写就自动找能量最强的一段")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    need = a.beats or (beats_needed(a.config) if a.config else 31)

    sys.path.insert(0, REA)
    from rea_video.audio import analyze_audio  # noqa: E402

    wav = to_wav(a.music)
    info = analyze_audio(wav)["music"]
    beats = np.array(info["beats"], dtype=np.float64)
    x, sr = read_wav(wav)
    Path(wav).unlink(missing_ok=True)
    if len(beats) < need + 1:
        sys.exit(f"这首歌只测出 {len(beats)} 拍，不够 {need} 拍，换一首或者减少场景")

    def rms(t0: float, t1: float) -> float:
        seg = x[int(t0 * sr):int(t1 * sr)]
        return float(np.sqrt(np.mean(seg ** 2) + 1e-12))

    if a.start_beat is None:                                             # 从小节头（每 4 拍）里挑最响的一段，开头也要有力
        cands = range(0, len(beats) - need, 4)
        i0 = max(cands, key=lambda i: rms(beats[i], beats[i + need - 1]) + 0.5 * rms(beats[i], beats[i + 2]))
    else:
        i0 = a.start_beat
    sel = beats[i0:i0 + need]

    flux, ft = onset_flux(x, sr)
    period = float(np.median(np.diff(sel)))

    def score(times):
        return float(np.mean([flux[(ft >= s - 0.02) & (ft <= s + 0.03)].max(initial=0) for s in times]))

    offs = np.arange(-period / 2, period / 2 + 1e-6, 0.005)
    best = float(offs[int(np.argmax([score(sel + o) for o in offs]))])
    sel = sel + best

    out = Path(a.out or Path(a.config).with_name("beats.json") if a.config else "beats.json")
    json.dump({"music": str(a.music), "bpm": info.get("tempo_bpm"), "start_beat": int(i0),
               "phase_offset": round(best, 3), "beats": [round(float(b), 4) for b in sel]},
              open(out, "w"), indent=1)
    print(f"BPM {info.get('tempo_bpm')}  用第 {i0} 拍起的 {need} 拍：{sel[0]:.2f}s – {sel[-1]:.2f}s"
          f"（共 {sel[-1] - sel[0]:.1f}s）  相位微调 {best * 1000:+.0f}ms  → {out}")


if __name__ == "__main__":
    main()
