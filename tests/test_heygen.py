"""本地测试 HeyGen 数字人：不连 HeyGen，用假接口返回 ffmpeg 合成的口播视频。
用法: DATA_DIR=/某个测试目录 python3 -I tests/test_heygen.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("HEYGEN_API_KEY", "hg-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import editor  # noqa: E402
import heygen  # noqa: E402

heygen.POLL = 0
clip = Path(tempfile.mkdtemp()) / "avatar.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=25:d=4",
                "-f", "lavfi", "-i", "sine=f=200:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(clip)], check=True)
log = {"post": None, "polls": 0}


class R:
    def __init__(self, js=None, data=b"", code=200):
        self._js, self._data, self.status_code = js, data, code
        self.text = json.dumps(js, ensure_ascii=False) if js else ""

    def json(self):
        return self._js

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def get(url, headers=None, params=None, timeout=None, stream=False):
    if url.endswith("/v2/avatars"):
        assert headers["X-Api-Key"] == "hg-test"
        return R({"data": {"avatars": [{"avatar_id": "me_avatar_01", "avatar_name": "我的数字人"},
                                       {"avatar_id": "Angela_public", "avatar_name": "Angela"}],
                           "talking_photos": [{"talking_photo_id": "tp1", "talking_photo_name": "照片"}]}})
    if url.endswith("/v2/voices"):
        return R({"data": {"voices": [{"voice_id": "v_zh", "name": "我的声音", "language": "Chinese"},
                                      {"voice_id": "v_en", "name": "Tom", "language": "English"}]}})
    if "video_status.get" in url:
        log["polls"] += 1
        done = log["polls"] >= 2
        return R({"data": {"status": "completed" if done else "processing",
                           "video_url": "https://cdn.example/x.mp4" if done else None}})
    if url == "https://cdn.example/x.mp4":
        assert headers is None, "下载 CDN 链接不应带 API Key"
        return R(data=clip.read_bytes())
    raise AssertionError(url)


def post(url, json=None, headers=None, timeout=None):  # noqa: A002
    log["post"] = (url, json)
    return R({"data": {"video_id": "hg_123"}})


heygen.requests.get, heygen.requests.post = get, post
av = heygen.list_avatars("我的")
assert [a["avatar_id"] for a in av["avatars"]] == ["me_avatar_01"], av
vs = heygen.list_voices()
assert [v["voice_id"] for v in vs] == ["v_zh"], vs
msgs = []
meta = heygen.generate("大家好，今天讲第一性原理。", avatar_id="me_avatar_01", voice_id="v_zh",
                       background="#00FF00", test=True, progress=msgs.append)
url, body = log["post"]
print(json.dumps(body, ensure_ascii=False))
assert url.endswith("/v2/video/generate") and body["aspect_ratio"] == "9:16" and body["test"] is True
it = body["video_inputs"][0]
assert it["character"] == {"type": "avatar", "avatar_id": "me_avatar_01", "avatar_style": "normal"}
assert it["voice"]["voice_id"] == "v_zh" and it["background"] == {"type": "color", "value": "#00FF00"}
print(msgs)
assert meta["has_audio"] and abs(meta["duration"] - 4) < 0.2 and meta["heygen"]["video_id"] == "hg_123"
assert (editor.VIDEOS / meta["video_id"] / "meta.json").exists()
for bad in ({"avatar_id": None, "talking_photo_id": None}, {"avatar_id": "a", "talking_photo_id": "b"}):
    try:
        heygen.generate("x", voice_id="v", **bad)
        raise AssertionError("应该报错")
    except editor.EditorError:
        pass
print("OK")
