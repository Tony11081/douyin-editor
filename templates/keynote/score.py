"""47 号「一根线」配乐：按 example.json 默认节奏（120 BPM，一拍 0.5 秒）合成一段原创配乐 + 卡画面的音效，输出 48kHz 立体声 wav。

用法：python3 -I score.py out.wav [总长秒数，默认 23]
结构：0–6 秒只有铺底和脉冲（悬念）→ 6–9 秒绣花：缝纫机针声 + 渐强的上升音 → 9 秒拉远揭晓：鼓、贝斯、琶音进来
→ 换产品处甩镜「嗖」→ 19.5 秒收：鼓停，和弦回落，21.35 秒打结「叮」一声，淡出。
时间点和 keynote.html 各场景的动画一一对应；场景时长改了，这里的 CUE 也要跟着改。
"""
from __future__ import annotations

import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
BEAT = 0.5
rng = np.random.default_rng(7)

CUE = {
    "thread_draw": (0.1, 2.1),        # 开场走针
    "statement_ul": (4.15, 4.85),     # 大字下划线
    "stitch": (6.35, 8.65),           # 缎面绣
    "drop": 9.0,                      # 拉远揭晓
    "whoosh": [11.72, 12.47, 13.22],  # 换产品甩镜
    "stat_ul": (14.5, 15.4),
    "outro": 19.5,
    "end_ul": (20.2, 21.3),
    "knot": 21.35,
}


def t_axis(d):
    return np.arange(int(d * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def add(buf, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= buf.shape[1]:
        return
    n = min(len(sig), buf.shape[1] - i)
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i:i + n] += sig[:n] * gain * l * 1.414
    buf[1, i:i + n] += sig[:n] * gain * r * 1.414


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, d, s, r, sustain_len):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    hold = max(0, int(sustain_len * SR) - a - d)
    e = np.concatenate([np.linspace(0, 1, a, False), np.linspace(1, s, d, False), np.full(hold, s), np.linspace(s, 0, r)])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def saw(f, t):
    return 2 * ((t * f) % 1) - 1


# ---------- 乐器 ----------
def pad_chord(notes, dur):
    t = t_axis(dur + 1.5)
    x = np.zeros_like(t)
    for n in notes:
        for det in (-0.09, 0.0, 0.11):
            x += saw(midi(n + det), t + rng.random())
    x = lp(x / (len(notes) * 3), 1500)
    return x * env_adsr(len(t), 0.6, 0.4, 0.8, 1.4, dur)


def pluck(n, dur=0.45):
    t = t_axis(dur)
    f = midi(n)
    x = 0.6 * np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 18) + 0.15 * saw(f, t)
    return lp(x, 4000) * np.exp(-t * 9)


def kick():
    t = t_axis(0.45)
    f = 45 + 95 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7) + 0.25 * hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 120)


def clap():
    t = t_axis(0.35)
    n = rng.standard_normal(len(t))
    e = np.zeros_like(t)
    for k, o in enumerate((0, 0.011, 0.022)):
        e += np.where(t >= o, np.exp(-(t - o) * (60 if k < 2 else 14)), 0)
    return bp(n, 900, 5000) * e * 0.6


def hat(open_=False):
    t = t_axis(0.25 if open_ else 0.06)
    return hp(rng.standard_normal(len(t)), 7000) * np.exp(-t * (14 if open_ else 70)) * 0.4


def bass(n, dur):
    t = t_axis(dur)
    f = midi(n)
    x = np.sin(2 * np.pi * f * t) + 0.35 * lp(saw(f, t), 600)
    return x * env_adsr(len(t), 0.005, 0.08, 0.7, 0.05, dur - 0.05)


def tick(bright=1.0):
    """缝纫机 / 针穿过布：短促的咔哒 + 一点金属共振。"""
    t = t_axis(0.07)
    click = hp(rng.standard_normal(len(t)), 2500) * np.exp(-t * 260)
    ring = np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 90) * 0.25 * bright
    thump = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 60) * 0.35
    return click * 0.8 + ring + thump


def whoosh(d=0.42):
    t = t_axis(d)
    n = rng.standard_normal(len(t))
    out = np.zeros_like(n)
    seg = 256
    for i in range(0, len(n), seg):
        c = 400 + 5000 * np.sin(np.pi * i / len(n))
        out[i:i + seg] = bp(n[max(0, i - 2048):i + seg], max(80, c * 0.5), min(20000, c * 1.6))[-len(n[i:i + seg]):]
    return out * np.sin(np.pi * t / d) ** 2


def riser(d):
    t = t_axis(d)
    n = rng.standard_normal(len(t))
    out = np.zeros_like(n)
    seg = 512
    for i in range(0, len(n), seg):
        c = 300 * (1 + 30 * (i / len(n)) ** 2)
        out[i:i + seg] = bp(n[max(0, i - 4096):i + seg], c * 0.7, min(20000, c * 1.4))[-len(n[i:i + seg]):]
    tone = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2 * t / d)) / SR) * 0.15
    return (out * 0.8 + tone) * (t / d) ** 2.2


def impact():
    t = t_axis(2.5)
    boom = np.sin(2 * np.pi * np.cumsum(40 + 60 * np.exp(-t * 9)) / SR) * np.exp(-t * 2.2)
    air = lp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 3) * 0.3
    return boom + air


def bell(n, d=3.0):
    t = t_axis(d)
    f = midi(n)
    x = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * k) for m, a, k in ((1, 1, 1.6), (2.76, 0.45, 3.5), (5.4, 0.25, 6), (8.9, 0.1, 9)))
    return x * (1 - np.exp(-t * 400))


def reverb(x, secs=2.2, wet=0.28):
    t = t_axis(secs)
    ir = rng.standard_normal((2, len(t))) * np.exp(-t * 6.5 / secs)
    ir = np.stack([lp(ir[0], 6000), lp(ir[1], 6000)])
    y = np.stack([fftconvolve(x[0], ir[0])[: x.shape[1]], fftconvolve(x[1], ir[1])[: x.shape[1]]])
    y /= np.max(np.abs(y)) + 1e-9
    return x * (1 - wet) + y * wet * np.max(np.abs(x))


def main(out: str, total: float = 23.0) -> None:
    N = int(total * SR)
    music, drums, sfx = (np.zeros((2, N)) for _ in range(3))
    # 和弦：每 2 秒一个（一小节），F maj9 → A m9 → C maj7 → G 6
    prog = [[53, 57, 60, 64, 67], [57, 60, 64, 67, 71], [48, 55, 59, 64, 67], [55, 59, 62, 64, 69]]
    roots = [41, 45, 36, 43]
    bar = 2.0
    for k in range(int(total / bar) + 1):
        at = k * bar
        ch = prog[k % 4]
        g = 0.5 if at < CUE["drop"] else 0.26
        if at >= CUE["outro"]:
            g = 0.3
        add(music, pad_chord(ch, bar), at, g, pan=-0.15)
        add(music, pad_chord([n + 12 for n in ch[2:]], bar), at, g * 0.35, pan=0.25)
    # 开场后的心跳脉冲（低音 + 极轻的拍）
    for b in np.arange(3.5, CUE["drop"], BEAT):
        add(drums, kick(), b, 0.42 if b < 6 else 0.55)
    # 揭晓之后：鼓、贝斯、琶音
    arp_pat = [0, 2, 4, 2, 3, 4, 2, 1]
    for i, b in enumerate(np.arange(CUE["drop"], CUE["outro"], BEAT / 2)):
        beat_i = int(round((b - CUE["drop"]) / BEAT * 2))
        k = int(b / bar) % 4
        if beat_i % 2 == 0:
            add(drums, kick(), b, 0.9)
            if (beat_i // 2) % 2 == 1:
                add(drums, clap(), b, 0.55, pan=0.05)
        add(drums, hat(beat_i % 4 == 2), b, 0.22 if beat_i % 2 else 0.12, pan=0.35)
        add(music, bass(roots[k], BEAT / 2 - 0.01), b, 0.38 if beat_i % 2 else 0.5)
        add(music, pluck(prog[k][arp_pat[i % 8]] + 12), b, 0.16, pan=(-0.4 if i % 2 else 0.4))
    add(sfx, impact(), CUE["drop"] - 0.02, 0.8)
    add(sfx, riser(CUE["drop"] - 7.0), 7.0, 0.55)
    # 结尾和弦回落 + 打结的「叮」
    add(music, pad_chord([53, 57, 60, 64, 69, 72], 3.5), CUE["outro"], 0.45)
    add(sfx, bell(81, 3.5), CUE["knot"], 0.7, pan=0.1)
    add(sfx, bell(76, 3.0), CUE["knot"] + 0.02, 0.2, pan=-0.2)
    # 针声
    def needle(a, b, rate, gain):
        for x in np.arange(a, b, 1 / rate):
            add(sfx, tick(0.6 + 0.4 * rng.random()), x + rng.normal(0, 0.004), gain * (0.8 + 0.4 * rng.random()), pan=rng.uniform(-0.2, 0.2))
    needle(*CUE["thread_draw"], 9, 0.6)
    needle(*CUE["statement_ul"], 11, 0.45)
    needle(*CUE["stitch"], 15, 0.75)
    needle(*CUE["stat_ul"], 11, 0.22)
    needle(*CUE["end_ul"], 10, 0.28)
    for w in CUE["whoosh"]:
        add(sfx, whoosh(), w - 0.12, 0.5, pan=-0.3)

    # 鼓的侧链：每个底鼓压一下音乐
    duck = np.ones(N)
    for b in np.arange(CUE["drop"], CUE["outro"], BEAT):
        i = int(b * SR)
        L = int(0.22 * SR)
        duck[i:i + L] = np.minimum(duck[i:i + L], 0.55 + 0.45 * np.linspace(0, 1, min(L, N - i)))
    music *= duck
    mix = reverb(music, 2.6, 0.32) + reverb(drums, 1.0, 0.1) + reverb(sfx, 1.6, 0.18)
    # 首尾淡入淡出
    fade_in, fade_out = int(0.4 * SR), int(1.8 * SR)
    mix[:, :fade_in] *= np.linspace(0, 1, fade_in)
    mix[:, -fade_out:] *= np.linspace(1, 0, fade_out)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix *= 0.89 / (np.max(np.abs(mix)) + 1e-9)
    wavfile.write(out, SR, (mix.T * 32767).astype(np.int16))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 23.0)
