"""本地测试 AI 生成视频：不连 OpenRouter，用假接口返回 ffmpeg 合成的视频。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_videogen.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import editor  # noqa: E402
import videogen  # noqa: E402

videogen.POLL = 0
tmp = Path(tempfile.mkdtemp())
clip = tmp / "gen.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=720x1280:r=24:d=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
png = tmp / "ref.png"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1",
                str(png)], check=True)
log = {"posts": [], "polls": 0}


class R:
    def __init__(self, code=200, js=None, data=b""):
        self.status_code, self._js, self._data = code, js, data
        self.text = json.dumps(js) if js is not None else ""
        self.headers = {}

    def json(self):
        return self._js

    def iter_content(self, n):
        yield self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def post(url, json=None, headers=None, timeout=None):  # noqa: A002
    log["posts"].append({"url": url, "body": json})
    return R(202, {"id": "vid_123", "status": "pending", "polling_url": url + "/vid_123"})


def get(url, params=None, headers=None, timeout=None, stream=False):
    assert headers["Authorization"] == "Bearer sk-or-test"
    if url.endswith("/content"):
        return R(200, data=clip.read_bytes())
    log["polls"] += 1
    st = "completed" if log["polls"] >= 3 else "in_progress"
    return R(200, {"id": "vid_123", "status": st, "usage": {"cost": 0.42}})


videogen.requests.post, videogen.requests.get = post, get
# Drive 链接的首帧图：服务器下载后转成 data URL
editor_download = editor.download
editor.download = lambda url, d: (Path(d) / "x.png").write_bytes(png.read_bytes()) and Path(d) / "x.png"
msgs = []
meta = videogen.generate("火箭缓缓升空，镜头慢慢推进", model="google/veo-3.1",
                         image_url="https://drive.google.com/file/d/abcdefghijk123/view",
                         duration=5, resolution="720p", progress=msgs.append)
editor.download = editor_download
body = log["posts"][0]["body"]
print(json.dumps({k: v for k, v in body.items() if k != "frame_images"}, ensure_ascii=False))
assert log["posts"][0]["url"].endswith("/videos")
assert body["aspect_ratio"] == "9:16" and body["generate_audio"] is False and body["duration"] == 5
fr = body["frame_images"][0]
assert fr["frame_type"] == "first_frame" and fr["image_url"]["url"].startswith("data:image/png;base64,")
print("progress:", msgs)
print(json.dumps(meta, ensure_ascii=False, indent=1))
assert meta["generated"]["cost"] == 0.42 and abs(meta["duration"] - 5) < 0.2

# 直链图片原样传
log["posts"].clear(); log["polls"] = 0
videogen.generate("测试", image_url="https://example.com/a.png")
assert log["posts"][0]["body"]["frame_images"][0]["image_url"]["url"] == "https://example.com/a.png"

# 生成镜头 + 另一条视频拼成一条成片
other = "mainvid0001"
d = editor.VIDEOS / other
d.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=6",
                "-f", "lavfi", "-i", "sine=f=220:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(d / "source.mp4")], check=True)
(d / "meta.json").write_text(json.dumps({"video_id": other, "name": "main", "url": "",
                                         "source": "source.mp4", **editor.probe(d / "source.mp4")}))
res = editor.render({"video_id": other, "preset": "veryfast", "effects": {"drift": 0},
                     "clips": [{"video_id": meta["video_id"], "text": "AI生成的镜头"},
                               {"start": 1, "end": 4, "text": "原片的一段"}]})
print(json.dumps({k: res[k] for k in ("duration", "captions")}, ensure_ascii=False))
assert abs(res["duration"] - 8) < 0.1, res["duration"]
info = editor.probe(editor.OUTPUTS / res["file"])
assert info["width"] == 1080 and info["height"] == 1920 and abs(info["duration"] - 8) < 0.2
assert res["captions"][0]["text"].startswith("AI生成")
print("OK")
