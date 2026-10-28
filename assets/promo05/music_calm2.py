"""05 车上道歉 · 原创配乐（numpy 合成）。安静走心：钢琴分解和弦 + 柔和铺底，
第二章加轻鼓和低音往前推，第三章收回到钢琴，最后一个和弦延长淡出。"""
import json, sys, wave
import numpy as np
from scipy import signal

SR = 48000
TOTAL = 84.13
DUR = TOTAL + 2.0
N = int(SR * DUR)
BAR = 19.17 / 8           # 第 2 章落在第 8 小节，第 3 章落在第 26 小节
B = BAR / 4
rng = np.random.default_rng(5)
L = np.zeros(N); R = np.zeros(N)

def add(x, t, g=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N: return
    x = x[: N - i]
    L[i:i+len(x)] += x * g * np.cos((pan+1)*np.pi/4) * np.sqrt(2)
    R[i:i+len(x)] += x * g * np.sin((pan+1)*np.pi/4) * np.sqrt(2)

def lp(x, fc, o=2): return signal.sosfilt(signal.butter(o, fc, "low", fs=SR, output="sos"), x)
def hp(x, fc, o=2): return signal.sosfilt(signal.butter(o, fc, "high", fs=SR, output="sos"), x)
def bp(x, a, b, o=2): return signal.sosfilt(signal.butter(o, [a, b], "band", fs=SR, output="sos"), x)

def hz(n):
    m = {"C":0,"C#":1,"D":2,"D#":3,"E":4,"F":5,"F#":6,"G":7,"G#":8,"A":9,"A#":10,"B":11}
    return 440 * 2 ** ((m[n[:-1]] + 12*(int(n[-1])+1) - 69) / 12)

def piano(f, dur=2.4, vel=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for k, (a, d) in enumerate([(1, 1.6), (0.45, 0.9), (0.22, 0.5), (0.12, 0.3), (0.06, 0.2)], 1):
        x += a * np.sin(2*np.pi*f*k*t*(1+0.0004*k*k)) * np.exp(-t/(d*(1.2 if f < 300 else 0.9)))
    x *= np.minimum(1, t/0.004)
    hammer = lp(rng.standard_normal(n), 3000) * np.exp(-t/0.006) * 0.04
    return (x + hammer) * vel * 0.32

def pad(freqs, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.08, 0.07):
            x += np.sin(2*np.pi*f*2**(det/12)*t + rng.random()*6) + 0.3*np.sin(2*np.pi*2*f*t)
    a = np.minimum(1, t/0.9) * np.minimum(1, np.maximum(0, (dur - t))/0.9)
    return lp(x, 1400) * a / len(freqs) * 0.5

def kick():
    n = int(0.5*SR); t = np.arange(n)/SR
    f = 48 + 70*np.exp(-t/0.03)
    return np.tanh(1.3*np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t/0.25))

def rim():
    n = int(0.12*SR); t = np.arange(n)/SR
    return (bp(rng.standard_normal(n), 1500, 4500)*np.exp(-t/0.02) + 0.4*np.sin(2*np.pi*1700*t)*np.exp(-t/0.015))

def shaker():
    n = int(0.09*SR); t = np.arange(n)/SR
    return hp(rng.standard_normal(n), 6000, 4) * np.sin(np.pi*t/t[-1])**2

def sub(f, dur):
    n = int(dur*SR); t = np.arange(n)/SR
    return np.sin(2*np.pi*f*t) * np.minimum(1, t/0.02) * np.exp(-t/(dur*0.7))

def chime(f=1760):
    n = int(2.5*SR); t = np.arange(n)/SR
    return (np.sin(2*np.pi*f*t) + 0.35*np.sin(2*np.pi*f*2.76*t)*np.exp(-t/0.4)) * np.exp(-t/1.0) * 0.4

def swell(dur):
    n = int(dur*SR); t = np.arange(n)/SR; k = t/dur
    nz = rng.standard_normal(n); out = np.zeros(n)
    for i in range(0, n, 2048):
        out[i:i+2048] = bp(nz[i:i+2048], 400+3000*k[i]**2, 900+7000*k[i]**2)
    return out * k**2.5 * 0.5

CH = [(["A3","C4","E4"], "A2"), (["F3","A3","C4"], "F2"), (["C4","E4","G4"], "C3"), (["G3","B3","D4"], "G2")]
S2, S3 = 19.17, 26 * BAR   # 第二章、第三章
END = 83.45                # 最后一个和弦（落在「谢谢」）
nbars = int(np.ceil(END / BAR))
for bar in range(nbars + 1):
    t0 = bar * BAR
    chord, root = CH[bar % 4]
    last = t0 >= END - 0.01 or bar == nbars
    if bar == nbars:
        t0 = END; chord, root = ["A3", "C4", "E4", "B4"], "A2"
    p = pad([hz(n) for n in chord], (BAR + 1.0) if not last else 3.0)
    add(p, t0, 0.55 if S2 <= t0 < S3 else 0.42, 0.0)
    # 钢琴：左手根音 + 右手分解
    add(piano(hz(root), 3.0, 0.9), t0, 1.0, -0.2)
    if last:
        for k, n in enumerate(chord):
            add(piano(hz(n)*2, 3.2, 0.7), t0 + 0.05*k, 1.0, 0.2)
        break
    pat = [0, 1, 2, 1, 0, 2, 1, 2]
    for e in range(8):
        tt = t0 + e * B / 2
        f = hz(chord[pat[e]]) * 2
        add(piano(f, 1.6, 0.55 if e % 2 else 0.75), tt, 1.0, 0.25 if e % 2 else -0.05)
    # 第二章：轻鼓 + 低音
    if S2 - 0.01 <= t0 < S3 - 0.01:
        for b in range(4):
            tb = t0 + b * B
            add(kick(), tb, 0.38 if b in (0, 2) else 0.0)
            if b in (1, 3): add(rim(), tb, 0.16, 0.15)
            add(shaker(), tb + B/2, 0.07, -0.3)
        add(sub(hz(root)/2, BAR*0.95), t0, 0.32)

# 点缀：开场一声、章节转换的气流、名词卡轻提示
add(chime(1760), 0.0, 0.35, 0.1)
add(swell(1.6), S2 - 1.6, 0.5)
add(swell(1.6), S3 - 1.6, 0.35)
add(chime(2093), S3, 0.2, -0.2)
for t in (8.9, 23.9, 43.4, 65.6):
    add(chime(2637), t, 0.10, 0.4)
add(chime(1318.5), 77.9, 0.18, 0.0)

def reverb(x, mix=0.3):
    out = np.zeros_like(x)
    for d, g in ((0.0297, .84), (0.0371, .83), (0.0411, .82), (0.0437, .81)):
        k = int(d*SR); a = np.zeros(k+1); a[0] = 1; a[k] = -g
        out += signal.lfilter([1], a, x)
    return x + mix * lp(out, 5000) / 4

L, R = reverb(L), reverb(R)
mix = np.stack([L, R], 1)
mix = hp(mix.T, 30).T
mix /= np.max(np.abs(mix)) + 1e-9
mix = np.tanh(1.1*mix) / np.tanh(1.1)
end = int((TOTAL + 0.6) * SR); fo = int(1.2 * SR)
mix[end-fo:end] *= np.linspace(1, 0, fo)[:, None]
mix = mix[:end]
pcm = (np.clip(mix, -1, 1) * 32000).astype("<i2")
with wave.open("score05b_raw.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("ok", len(mix)/SR)
