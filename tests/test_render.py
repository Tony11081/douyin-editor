"""本地测试：用合成视频 + 伪造转写跑通剪辑、字幕、BGM。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_render.py
（测试目录里需要 videos/testvideo01/source.mov 和 music/light.mp3）"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import editor  # noqa: E402

vid = "testvideo01"
d = editor.VIDEOS / vid
meta = {"video_id": vid, "name": "test", "url": "", "source": "source.mov", **editor.probe(d / "source.mov")}
(d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
print("probe:", {k: meta[k] for k in ("duration", "width", "height", "color_transfer")})

# 伪造转写：模拟口播「最主要就是便宜，很便宜。我在yellow88上找了一款爆品，五块钱进的。」
text = list("最主要就是便宜") + ["，"] + list("很便宜") + ["。"] + list("我在") + ["yellow", "88"] + \
       list("上找了一款爆品") + ["，"] + list("五块钱进的") + ["。"]
words, t = [], 0.5
for ch in text:
    if ch in "，。":
        words[-1]["w"] += ch
        t += 0.4
        continue
    words.append({"i": len(words), "s": round(t, 2), "e": round(t + 0.2, 2), "w": ch})
    t += 0.22
(d / "transcript.json").write_text(json.dumps(
    {"language": "zh", "segments": [{"s": 0.5, "e": t, "text": "".join(w["w"] for w in words),
                                     "w0": 0, "w1": len(words) - 1}], "words": words},
    ensure_ascii=False))
print(editor.transcript_text(editor.load_transcript(vid))[:300])

spec = {
    "video_id": vid,
    "clips": [
        {"start": 6.0, "end": 9.5, "zoom": 1.12},          # 重排：后半句提前
        {"start": 0.4, "end": 5.95},                        # 自动字幕 + 错字更正
        {"start": 9.6, "end": 11.5, "text": "这一段用手写字幕，Etsy上卖五十美金"},
    ],
    "corrections": {"yellow88": "1688"},
    "highlight_words": ["便宜", "1688", "五十美金"],
    "title": {"text": "代做产品图\n又好又快又便宜"},
    "bgm": {"name": "light.mp3", "volume": 0.1, "fade_out": 1.0},
    "preset": "veryfast", "color": {"saturation": 0.95, "warmth": 0.3},
}
msgs = []
res = editor.render(spec, msgs.append)
print("progress:", msgs)
print(json.dumps(res, ensure_ascii=False, indent=1))
out = editor.OUTPUTS / res["file"]
info = editor.probe(out)
print("output probe:", info)
assert info["width"] == 1080 and info["height"] == 1920
assert abs(info["duration"] - res["duration"]) < 0.2, (info["duration"], res["duration"])
assert any("1688" in c["text"] for c in res["captions"]), "错字更正没生效"
assert all(len(c["text"]) <= 14 for c in res["captions"]), "字幕太长"
# BGM 淡出：最后 0.3 秒音量应明显低于中段
def vol(ss, dur):
    p = subprocess.run(["ffmpeg", "-ss", str(ss), "-t", str(dur), "-i", str(out), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    return float(p.stderr.split("mean_volume:")[1].split("dB")[0])
print("mean vol mid / last:", vol(3, 1), vol(res["duration"] - 0.25, 0.25))
for i, img in enumerate(editor.frames("output", res["output_id"], [0.8, 4.5, res["duration"] - 1], 540)):
    Path(os.environ["DATA_DIR"], f"frame{i}.jpg").write_bytes(img)
print("OK")
