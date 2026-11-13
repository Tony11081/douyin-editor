"""配音句尾杂音清理：句子念完、停顿之后多出来的一小段声音要剪掉，正常的句子不能动。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_tts_tail.py"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import tts  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def make(name: str, parts: list[tuple[str, float]]) -> Path:
    """parts: [("tone" 或 "sil", 秒数), …] 拼成一个 wav。"""
    ins, lab = [], []
    for k, (kind, d) in enumerate(parts):
        src = f"sine=f=300:d={d}:r=48000" if kind == "tone" else f"anullsrc=r=48000:cl=mono:d={d}"
        ins += ["-f", "lavfi", "-t", str(d), "-i", src]
        lab.append(f"[{k}:a]")
    out = tmp / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex",
                    "".join(lab) + f"concat=n={len(parts)}:v=0:a=1,volume=0.5[a]",
                    "-map", "[a]", "-c:a", "pcm_s16le", str(out)], check=True)
    return out


# 1) 正文 2 秒 → 静 0.8 秒 → 0.25 秒杂音：杂音剪掉，正文留着（没装 Whisper 也剪：停得久、声音短）
w = make("stray.wav", [("tone", 2.0), ("sil", 0.8), ("tone", 0.25)])
r = tts._clean_tail(w, "测试")
assert 0.9 < r["cut"] < 1.1 and not r["pauses"] and not r["suspect"], r
assert abs(tts._duration(w) - 2.06) < 0.05, tts._duration(w)
# 2) 正文 → 静 0.8 秒 → 又是 1 秒正文：不剪，只提醒长停顿
w = make("pause.wav", [("tone", 2.0), ("sil", 0.8), ("tone", 1.0)])
r = tts._clean_tail(w, "测试")
assert r["cut"] == 0 and len(r["pauses"]) == 1 and abs(r["pauses"][0][0] - 2.0) < 0.1, r
assert abs(tts._duration(w) - 3.8) < 0.05
# 3) 正常的短停顿 + 短结尾：不剪、不提醒
w = make("normal.wav", [("tone", 2.0), ("sil", 0.3), ("tone", 0.25)])
r = tts._clean_tail(w, "测试")
assert r == {"cut": 0.0, "suspect": 0.0, "pauses": []}, r
# 4) 没有任何停顿
w = make("plain.wav", [("tone", 1.5)])
assert tts._clean_tail(w, "测试") == {"cut": 0.0, "suspect": 0.0, "pauses": []}

# 5) 装了 Whisper 时按听写结果决定：停 0.6 秒后的 0.5 秒是正文（「……，我发给你」），剪了会少字 → 不剪
import types  # noqa: E402

sys.modules.setdefault("faster_whisper", types.ModuleType("faster_whisper"))
tts.editor.whisper_file = lambda p: "评论区打属性两个字我发给你" if tts._duration(p) > 3.2 else "评论区打属性两个字"
w = make("real_tail.wav", [("tone", 2.4), ("sil", 0.6), ("tone", 0.5)])
r = tts._clean_tail(w, "评论区打属性两个字，我发给你。")
assert r["cut"] == 0 and abs(tts._duration(w) - 3.5) < 0.05, r
assert not (tmp / "real_tail.cut.wav").exists()
# 6) 同样的形状，但剪不剪听写都一样（多出来的是杂音）→ 剪
tts.editor.whisper_file = lambda p: "就在图片的文件属性里"
w = make("stray2.wav", [("tone", 2.4), ("sil", 0.8), ("tone", 0.25)])
r = tts._clean_tail(w, "就在图片的文件属性里。")
assert 0.9 < r["cut"] < 1.1 and abs(tts._duration(w) - 2.46) < 0.05, r

# 7) 句首 0.12 秒杂音 + 停 0.2 秒 + 正文：听写多一个「的」，剪掉更接近原文 → 剪
tts.editor.whisper_file = lambda p: "的办法是上传之前" if tts._duration(p) > 2.25 else "办法是上传之前"
w = make("head.wav", [("tone", 0.12), ("sil", 0.2), ("tone", 2.0)])
r = tts._clean_head(w, "办法是，上传之前")
assert 0.25 < r["cut"] < 0.33 and abs(tts._duration(w) - 2.04) < 0.05, (r, tts._duration(w))
# 8) 同样的形状，但开头是正文（「对，……」），剪了少字 → 不剪，标出来
tts.editor.whisper_file = lambda p: "对上传之前" if tts._duration(p) > 2.25 else "上传之前"
w = make("head_real.wav", [("tone", 0.2), ("sil", 0.2), ("tone", 2.0)])
r = tts._clean_head(w, "对，上传之前")
assert r["cut"] == 0 and r["suspect"] > 0 and abs(tts._duration(w) - 2.4) < 0.05, r
# 9) 开头第一段就是正常的词（0.6 秒）：不碰
w = make("head_normal.wav", [("tone", 0.6), ("sil", 0.3), ("tone", 2.0)])
assert tts._clean_head(w, "实拍图，只是") == {"cut": 0.0, "suspect": 0.0}
print("OK")
