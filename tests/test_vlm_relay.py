"""本地测试看图转发：不连 OpenRouter，用假的 urlopen 代替。
用法: python3 -I tests/test_vlm_relay.py"""
import io
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
os.environ["VLM_RELAY_PORT"] = "18791"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import vlm_relay  # noqa: E402

sent = []


class FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_open(req, timeout=None):
    sent.append({"url": req.full_url, "auth": req.get_header("Authorization"), "body": json.loads(req.data)})
    return FakeResp(json.dumps({"choices": [{"message": {"content": "{}"}}],
                                "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.0006}}).encode())


msg = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

# 1. 白名单外的模型被拒
try:
    vlm_relay.prepare({"model": "openai/gpt-5", "messages": msg})
    raise AssertionError("应该拒绝白名单外的模型")
except vlm_relay.RelayError as e:
    assert e.status == 403

# 2. 没写模型用默认；超长 max_tokens 被压到上限；强制非流式并要求返回花费
p = vlm_relay.prepare({"messages": msg, "max_tokens": 10**6, "stream": True})
assert p["model"] == "google/gemini-3.1-flash-lite" and p["max_tokens"] == vlm_relay.MAX_TOKENS
assert p["stream"] is False and p["usage"] == {"include": True}

# 2b. 视频片段从 image_url 改成 video_url，图片保持不变
vm = [{"role": "user", "content": [{"type": "text", "text": "x"},
                                   {"type": "image_url", "image_url": {"url": "data:video/mp4;base64,AAAA"}},
                                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB"}}]}]
pv = vlm_relay.prepare({"messages": vm})["messages"][0]["content"]
assert pv[1] == {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAA"}}, pv[1]
assert pv[2]["type"] == "image_url" and vm[0]["content"][1]["type"] == "image_url"  # 不改原请求

# 3. 转发时用服务端密钥，记下花费
status, data = vlm_relay.forward({"model": "google/gemini-3.1-flash-lite", "messages": msg, "max_tokens": 500},
                                 opener=fake_open)
assert status == 200 and sent[0]["auth"] == "Bearer sk-or-test"
assert sent[0]["url"].endswith("/chat/completions") and sent[0]["body"]["max_tokens"] == 500
s = vlm_relay.usage_summary()
assert s["calls"] == 1 and s["cost_usd"] == 0.0006 and s["prompt_tokens"] == 1000, s

# 4. 真起一个本机服务：只听 127.0.0.1，模型列表和错误路径正常
vlm_relay.forward.__defaults__ = (fake_open,)
srv = vlm_relay.start()
assert srv is not None and srv.server_address[0] == "127.0.0.1"
base = f"http://127.0.0.1:{vlm_relay.PORT}"
models = json.loads(urllib.request.urlopen(base + "/v1/models").read())
assert models["data"][0]["id"] == "google/gemini-3.1-flash-lite"
req = urllib.request.Request(base + "/v1/chat/completions", method="POST",
                             data=json.dumps({"messages": msg}).encode(),
                             headers={"Content-Type": "application/json", "Authorization": "Bearer local-relay"})
out = json.loads(urllib.request.urlopen(req).read())
assert out["usage"]["cost"] == 0.0006 and sent[-1]["auth"] == "Bearer sk-or-test"
try:
    urllib.request.urlopen(urllib.request.Request(base + "/v1/chat/completions", method="POST",
                                                  data=json.dumps({"model": "x/y", "messages": msg}).encode()))
    raise AssertionError("应该 403")
except urllib.error.HTTPError as e:
    assert e.code == 403
srv.shutdown()
print("vlm_relay ok", vlm_relay.usage_summary())
