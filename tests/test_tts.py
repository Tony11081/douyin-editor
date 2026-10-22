"""本地测试 AI 配音：不连 OpenRouter，用 ffmpeg 合成的假语音代替接口返回。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_tts.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import editor  # noqa: E402
import tts  # noqa: E402

calls = []


class FakeResp:
    def __init__(self, data: bytes):
        self.status_code, self.content, self.headers = 200, data, {"Content-Type": "audio/mpeg"}


def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
    calls.append({"url": url, "body": json, "auth": headers["Authorization"]})
    # 0.4 秒静音 + 按字数长度的"语音" + 0.5 秒静音，测试首尾静音裁剪
    dur = 0.2 * len(json["input"])
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=f=300:d={dur}:r=24000", "-af",
                        "adelay=400,apad=pad_dur=0.5,volume=0.5", "-c:a", "libmp3lame", f.name],
                       check=True)
        return FakeResp(Path(f.name).read_bytes())


tts.requests.post = fake_post
segs = ["第一句：原材料只占百分之二。", "第二句话稍微长一点，用来测试字幕切分是否正常。", "完。"]
meta = tts.synthesize(segs, voice="alloy", instructions="沉稳讲解", gap=0.3)
print(json.dumps({k: meta[k] for k in ("tts_id", "total", "segments")}, ensure_ascii=False, indent=1))
assert calls[0]["url"].endswith("/audio/speech") and calls[0]["body"]["voice"] == "alloy"
assert calls[0]["body"]["instructions"] == "沉稳讲解" and calls[0]["auth"] == "Bearer sk-or-test"
for it, s in zip(meta["segments"], segs):
    expect = 0.2 * len(s)
    assert abs(it["duration"] - expect) < 0.15, ("静音没裁干净", it["duration"], expect)
assert tts.preview(meta["tts_id"]).exists()

# 无声的动画视频 + 配音 + 自动字幕
vid = "ttsvideo01"
d = editor.VIDEOS / vid
d.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=12",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "source.mp4")], check=True)
m = {"video_id": vid, "name": "anim", "url": "", "source": "source.mp4", **editor.probe(d / "source.mp4")}
(d / "meta.json").write_text(json.dumps(m))
assert not m["has_audio"]
at = [0.5, 3.5, 10.0]
res = editor.render({"video_id": vid, "voiceover": {"tts_id": meta["tts_id"], "at": at},
                     "corrections": {"百分之二": "2%"}, "highlight_words": ["2%"],
                     "effects": {"drift": 0, "sfx": False}, "preset": "veryfast"})
print(json.dumps({k: res[k] for k in ("duration", "voiceover", "captions")}, ensure_ascii=False, indent=1))
assert [v["start"] for v in res["voiceover"]] == at
assert any("2%" in c["text"] for c in res["captions"]), "字幕没用上 corrections"
assert res["captions"][0]["start"] >= 0.45, "第一条字幕应该在配音开始时出现"
assert all(len(c["text"]) <= 14 for c in res["captions"])
out = editor.OUTPUTS / res["file"]


def vol(ss, dur):
    p = subprocess.run(["ffmpeg", "-ss", str(ss), "-t", str(dur), "-i", str(out), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    return float(p.stderr.split("mean_volume:")[1].split("dB")[0])


quiet, loud = vol(0.0, 0.4), vol(1.0, 1.0)
print("mean vol before voice / during voice:", quiet, loud)
assert loud > quiet + 20, "配音没有铺到对应位置"
# 句数和 at 不一致时要报错
try:
    editor.render({"video_id": vid, "voiceover": {"tts_id": meta["tts_id"], "at": [0, 1]}})
    raise AssertionError("应该报错")
except editor.EditorError as e:
    print("expected error:", e)
# mux：只加声音，画面必须逐帧和原片一样（视频流原样复制）
music = editor.MUSIC / "bed.mp3"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=660:d=30", "-c:a", "libmp3lame",
                str(music)], check=True)
mres = editor.mux({"video_id": vid, "voiceover": {"tts_id": meta["tts_id"], "at": at},
                   "bgm": {"name": "bed.mp3", "volume": 0.1}})
mout = editor.OUTPUTS / mres["file"]


def vhash(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
                        "-f", "hash", "-hash", "md5", "-"], capture_output=True, text=True)
    return p.stdout.strip()


assert mres["video_copied"] and vhash(mout) == vhash(d / "source.mp4"), "mux 改动了画面"
minfo = editor.probe(mout)
assert minfo["has_audio"] and abs(minfo["duration"] - 12) < 0.15, minfo
out = mout
print("mux vol before voice / during voice:", vol(0.0, 0.4), vol(1.0, 1.0))
assert vol(1.0, 1.0) > vol(0.0, 0.4) + 6, "配音没铺上"
# mux speed：1.5 倍速，时长缩短、配音位置按比例前移、帧率不变
sres = editor.mux({"video_id": vid, "voiceover": {"tts_id": meta["tts_id"], "at": at},
                   "bgm": {"name": "bed.mp3", "volume": 0.1}, "speed": 1.5})
sout = editor.OUTPUTS / sres["file"]
sinfo = editor.probe(sout)
assert not sres["video_copied"] and sres["speed"] == 1.5
assert abs(sinfo["duration"] - 8) < 0.15, sinfo
assert sinfo["fps"] == editor.probe(d / "source.mp4")["fps"], sinfo
assert [round(v["start"], 2) for v in sres["voiceover"]] == [round(x / 1.5, 2) for x in at]
assert sres["checks"]["ok"], sres["checks"]
out = sout
first = at[0] / 1.5
print("speed vol before voice / during voice:", vol(0.0, 0.25), vol(first + 0.3, 0.5))
assert vol(first + 0.3, 0.5) > vol(0.0, 0.25) + 6, "变速后配音位置不对"
try:
    editor.mux({"video_id": vid, "bgm": {"name": "bed.mp3"}, "speed": 3})
    raise AssertionError("speed 超范围应该报错")
except Exception as e:  # noqa: BLE001
    assert "speed" in str(e), e
print("OK")
