"""严格模式测试：写错、越界、做不到的指令必须报错；预演和成片自检要准确。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_strict.py"""
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

vid = "strictvid01"
d = editor.VIDEOS / vid
d.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=10",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "source.mp4")], check=True)
(d / "meta.json").write_text(json.dumps({"video_id": vid, "name": "s", "url": "", "source": "source.mp4",
                                         **editor.probe(d / "source.mp4")}))


class FakeResp:
    def __init__(self, data):
        self.status_code, self.content, self.headers = 200, data, {"Content-Type": "audio/mpeg"}


def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.5:r=24000",
                        "-af", "volume=0.5", "-c:a", "libmp3lame", f.name], check=True)
        return FakeResp(Path(f.name).read_bytes())


tts.requests.post = fake_post
tm = tts.synthesize(["第一句话在这里", "第二句话也在这里"])
assert tm["verify"]["status"] in ("skipped", "ok", "needs_review")


def must_fail(spec, *expect):
    try:
        editor.render(spec, dry_run=True)
    except editor.EditorError as e:
        msg = str(e)
        for x in expect:
            assert x in msg, (x, msg)
        print("  拒绝 ✓", msg.splitlines()[-1][:90])
        return
    raise AssertionError(f"应该报错：{spec}")


print("错误指令必须被拒绝：")
must_fail({"video_id": vid, "captoins": "none"}, "captoins", "captions")          # 拼错参数名，给出建议
must_fail({"video_id": vid, "captions": "none", "clips": [{"start": 0, "end": 3, "zoom": 0.8}]}, "zoom")
must_fail({"video_id": vid, "captions": "none", "clips": [{"start": 0, "end": 12}]}, "超过视频")
must_fail({"video_id": vid, "captions": "none", "clips": [{"start": 5, "end": 4}]}, "start ≥ end")
must_fail({"video_id": vid, "captions": "none", "bgm": {"name": "不存在.mp3"}}, "音乐库里没有")
must_fail({"video_id": vid, "captions": "none", "title": {"duration": 3}}, "缺少必填项 text")
must_fail({"video_id": vid, "captions": "none", "caption_style": {"color": "white"}}, "#RRGGBB")
must_fail({"video_id": vid, "captions": "none", "effects": {"drift": "0"}}, "drift")
must_fail({"video_id": vid, "voiceover": {"tts_id": tm["tts_id"], "at": [0.5]}}, "有 1 个时间")
must_fail({"video_id": vid, "voiceover": {"tts_id": tm["tts_id"], "at": [0.5, 1.0]}}, "重叠")
must_fail({"video_id": vid, "voiceover": {"tts_id": tm["tts_id"], "at": [0.5, 9.0]}}, "超出成片时长")
must_fail({"video_id": vid}, "还没有转写")                                       # 不猜字幕来源
must_fail({"video_id": vid, "captions": "voiceover"}, "没有 voiceover")

print("预演：")
spec = {"video_id": vid, "clips": [{"start": 1, "end": 4}, {"start": 6, "end": 9.5, "zoom": 1.1}],
        "voiceover": {"tts_id": tm["tts_id"], "at": [0.3, 3.4]},
        "highlight_words": ["第二句", "不存在的词"], "effects": {"drift": 0, "sfx": False}, "preset": "veryfast"}
plan = editor.render(json.loads(json.dumps(spec)), dry_run=True)
print(json.dumps({k: plan[k] for k in ("duration", "timeline", "warnings")}, ensure_ascii=False))
assert plan["duration"] == 6.5
assert [(t["out_start"], t["out_end"]) for t in plan["timeline"]] == [(0.0, 3.0), (3.0, 6.5)]
assert plan["applied"]["caption_mode"] == "voiceover"
assert "flash_first" in plan["applied"]["effects_defaults_used"]
assert any("不存在的词" in w for w in plan["warnings"])
assert [v["start"] for v in plan["voiceover"]] == [0.3, 3.4]

print("渲染 + 自检：")
res = editor.render(json.loads(json.dumps(spec)))
for c in res["checks"]["items"]:
    print("  ", "✓" if c["ok"] else "✗", c["check"], c["detail"])
assert res["checks"]["ok"], res["checks"]
assert res["applied"]["duration"] == 6.5
print("OK")
