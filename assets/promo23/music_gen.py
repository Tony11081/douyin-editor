"""01 产品图代制作 · 原创配乐（numpy 合成）。

124 BPM tech-house，A 小调 Am-F-C-G。第一拍落在 0.76s 的「便宜」重击上，
所有音效（嗖、叮、重击、上升音）都对齐动画节点。输出 score.wav（48k 立体声）。
"""
import numpy as np
from scipy import signal

import json, sys
SR = 48000
CFG = json.load(open(sys.argv[1]))
TOTAL = CFG["total"]
DUR = TOTAL + 1.2
N = int(SR * DUR)
BPM = CFG["bpm"]
B = 60 / BPM
T0 = CFG["t0"]
rng = np.random.default_rng(CFG.get("seed", 7))

L = np.zeros(N)
R = np.zeros(N)


def add(x, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N or i + len(x) <= 0:
        return
    if i < 0:
        x, i = x[-i:], 0
    x = x[: N - i]
    l = gain * np.cos((pan + 1) * np.pi / 4)
    r = gain * np.sin((pan + 1) * np.pi / 4)
    L[i:i + len(x)] += x * l * np.sqrt(2)
    R[i:i + len(x)] += x * r * np.sqrt(2)


def env(n, a=0.002, d=0.2, sus=0.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * (sus + (1 - sus) * np.exp(-t / d))
    return e


def lp(x, fc, order=2):
    sos = signal.butter(order, min(fc, SR / 2 - 100), "low", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def hp(x, fc, order=2):
    sos = signal.butter(order, fc, "high", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], "band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def saw(f, n, phase=0.0):
    t = np.arange(n) / SR
    return 2 * ((f * t + phase) % 1) - 1


def note(name):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    p, o = name[:-1], int(name[-1])
    return 440 * 2 ** ((names[p] + 12 * (o + 1) - 69) / 12)


# ---------------------------------------------------------------- 乐器
def kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / 0.28)
    click = hp(rng.standard_normal(n), 3000) * np.exp(-t / 0.004) * 0.35
    return np.tanh(1.6 * (x + click))


def clap():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    nz = bp(rng.standard_normal(n), 900, 3200)
    e = np.zeros(n)
    for k, d in enumerate([0, 0.011, 0.022]):
        i = int(d * SR)
        e[i:] += np.exp(-(t[: n - i]) / 0.006) * (0.7 if k < 2 else 1)
    e += np.exp(-np.maximum(0, t - 0.022) / 0.12) * (t > 0.022) * 0.8
    return nz * e * 0.9


def hat(open_=False):
    n = int((0.22 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    x = hp(rng.standard_normal(n), 7500, 4) * np.exp(-t / (0.07 if open_ else 0.014))
    return x


def bass(f, dur):
    n = int(dur * SR)
    x = saw(f, n) + 0.5 * saw(f * 0.5, n)
    x = lp(x, 520) * env(n, 0.003, dur * 0.6, 0.35)
    return np.tanh(1.8 * x) * 0.9


def pad(freqs, dur):
    n = int(dur * SR)
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            x += saw(f * 2 ** (det / 12), n, rng.random())
    x = lp(x / (len(freqs) * 3), 2200)
    t = np.arange(n) / SR
    a = np.minimum(1, t / 0.08) * np.minimum(1, (dur - t) / 0.12 + 0.0)
    return x * np.clip(a, 0, 1)


def pluck(f, dur=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = saw(f, n) * 0.6 + np.sign(np.sin(2 * np.pi * f * 2 * t)) * 0.25
    # 滤波包络：先亮后暗
    bright = lp(x, 5000)
    dark = lp(x, 900)
    m = np.exp(-t / 0.05)
    return (bright * m + dark * (1 - m)) * np.exp(-t / 0.11)


def impact(big=True):
    n = int((2.2 if big else 1.0) * SR)
    t = np.arange(n) / SR
    f = 38 + 90 * np.exp(-t / 0.08)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.55 if big else 0.25))
    crash = lp(hp(rng.standard_normal(n), 300), 7000) * np.exp(-t / (0.9 if big else 0.3)) * 0.45
    return np.tanh(2.0 * boom) * 0.9 + crash


def riser(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    k = t / dur
    nz = rng.standard_normal(n)
    # 分段扫高通，模拟滤波上升
    out = np.zeros(n)
    seg = 2048
    for i in range(0, n, seg):
        fc = 300 + 7000 * (k[i] ** 2)
        out[i:i + seg] = hp(nz[i:i + seg], fc)
    sweep = np.sin(2 * np.pi * np.cumsum(220 + 1400 * k ** 2) / SR) * 0.25
    return (out * 0.6 + sweep) * (k ** 2.2)


def whoosh(dur=0.42, up=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    k = t / dur
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    seg = 1024
    for i in range(0, n, seg):
        c = 600 + 5000 * (k[i] if up else 1 - k[i])
        out[i:i + seg] = bp(nz[i:i + seg], c * 0.6, min(c * 1.6, 20000))
    return out * np.sin(np.pi * k) ** 1.5


def ding(f=1568):
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    mod = np.sin(2 * np.pi * f * 3.5 * t) * 2.2 * np.exp(-t / 0.08)
    x = np.sin(2 * np.pi * f * t + mod) * np.exp(-t / 0.35)
    x += 0.4 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.15)
    return x * 0.5


def tick():
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 4000) * np.exp(-t / 0.004)


# ---------------------------------------------------------------- 编排（配置驱动）
CHORDS = [(c["notes"], c["root"]) for c in CFG["chords"]]
BAR = 4 * B
nbars = int(np.ceil((DUR - T0) / BAR)) + 1
BREAK = tuple(CFG.get("break", (1e9, 1e9)))
END_HIT = CFG["end_hit"]
STOP = CFG.get("hard_stop", False)


def in_break(t):
    return BREAK[0] <= t < BREAK[1]


duck = np.ones(N)
K = kick()
CL = clap()
for beat in range(int((DUR - T0) / B) + 1):
    t = T0 + beat * B
    if t > END_HIT + 0.05:
        break
    if in_break(t):
        if beat % 2 == 0:
            add(lp(K, 400), t, 0.5)
        else:
            add(lp(CL, 2500), t, 0.2)
        continue
    add(K, t, 0.95)
    i = int(t * SR)
    dn = int(0.32 * SR)
    seg = 1 - 0.65 * np.exp(-np.arange(dn) / SR / 0.09)
    duck[i:i + dn] = np.minimum(duck[i:i + dn], seg[: max(0, min(dn, N - i))])
    if beat % 4 in (1, 3):
        add(CL, t, 0.55, 0.05)
    add(hat(True), t + B / 2, 0.22, 0.25)
    for s in (0.25, 0.75):
        add(hat(False), t + B * s, 0.09, -0.3)

if T0 > 0.3:
    add(riser(T0), 0.0, 0.5)

padbus_L = np.zeros(N)
padbus_R = np.zeros(N)
for bar in range(nbars):
    t_bar = T0 + bar * BAR
    if t_bar > END_HIT + 0.1:
        break
    chord, root = CHORDS[bar % len(CHORDS)]
    fr = note(root)
    p = pad([note(n) for n in chord], BAR + 0.05)
    if STOP:
        p = p[: max(0, int((END_HIT - t_bar) * SR))]
    i = int(t_bar * SR)
    m = min(len(p), N - i)
    if m > 0:
        padbus_L[i:i + m] += p[:m] * 0.32
        padbus_R[i:i + m] += np.roll(p, 240)[:m] * 0.32
    for e in range(8):
        t = t_bar + e * B / 2
        if t > END_HIT - 0.02 or in_break(t):
            continue
        if e % 2 == 1:
            add(bass(fr, B / 2 * 0.9), t, 0.42)
    arp = [note(n) * 2 for n in chord] + [note(chord[1]) * 4]
    for s in range(16):
        t = t_bar + s * B / 4
        if t > END_HIT - 0.02:
            break
        g = 0.13 if in_break(t) else 0.10
        add(pluck(arp[(s * 3) % len(arp)]), t, g, 0.45 if s % 2 else -0.45)

L += padbus_L * duck
R += padbus_R * duck

FX = {"impact": lambda: impact(True), "impact_s": lambda: impact(False), "whoosh": lambda: whoosh(0.42),
      "whoosh_d": lambda: whoosh(0.45, False), "ding": lambda: ding(2093), "ding_h": lambda: ding(2637),
      "tick": tick}
for h in CFG["hits"]:
    kind, t = h[0], h[1]
    g = h[2] if len(h) > 2 else 0.4
    pan = h[3] if len(h) > 3 else 0.0
    if kind == "riser":
        add(riser(h[4]), t, g, pan)
    else:
        add(FX[kind](), t, g, pan)
# ---------------------------------------------------------------- 简易混响 + 母带
def reverb(x, mix=0.16):
    out = np.zeros_like(x)
    for d, g in ((0.0297, 0.80), (0.0371, 0.78), (0.0411, 0.76), (0.0437, 0.74)):
        k = int(d * SR)
        a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out += signal.lfilter([1], a, x)
    for d, g in ((0.005, 0.7), (0.0017, 0.7)):
        k = int(d * SR)
        b = np.zeros(k + 1); b[0] = -g; b[k] = 1
        a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out = signal.lfilter(b, a, out)
    return x + mix * lp(out, 6000) / 4


L, R = reverb(L), reverb(R)
mix = np.stack([L, R], 1)
mix = hp(mix.T, 28).T
mix /= np.max(np.abs(mix)) + 1e-9
mix = np.tanh(1.3 * mix) / np.tanh(1.3)
# 结尾 0.4s 淡出
fo = int(0.4 * SR)
end = int((TOTAL + 0.9) * SR)
mix[end - fo:end] *= np.linspace(1, 0, fo)[:, None]
mix[end:] = 0
mix = mix[: end]

import wave
pcm = (np.clip(mix, -1, 1) * 32000).astype("<i2")
with wave.open(CFG["out"], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("ok", mix.shape[0] / SR, "s")
