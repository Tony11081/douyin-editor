"""本机看图转发：给同一台服务器上的 rea-video（视频逆向拆解）调用 OpenRouter 的看图模型。

- 只监听 127.0.0.1，不经过 Caddy/nginx，外网访问不到。
- OpenRouter 密钥只在本服务进程里（.env 的 OPENROUTER_API_KEY），rea-video 那边只配一个占位密钥。
- 只放行白名单里的模型（VLM_RELAY_MODELS，默认 google/gemini-3.1-flash-lite），并限制单次输出长度。
- 每次调用的 token 数和花费记到 DATA_DIR/vlm_usage.jsonl，方便统计每条视频花了多少钱。

rea-video 的配置：REA_VLM_BASE_URL=http://127.0.0.1:8791/v1、REA_VLM_API_KEY=local-relay（随便写）、
REA_VLM_MODEL=google/gemini-3.1-flash-lite。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("VLM_RELAY_PORT", "8791"))
MODELS = [m.strip() for m in os.environ.get("VLM_RELAY_MODELS", "google/gemini-3.1-flash-lite").split(",")
          if m.strip()]
API_BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MAX_BODY = int(os.environ.get("VLM_RELAY_MAX_MB", "40")) * 1024 * 1024   # 带视频片段的请求会比较大
MAX_TOKENS = int(os.environ.get("VLM_RELAY_MAX_TOKENS", "8192"))
TIMEOUT = float(os.environ.get("VLM_RELAY_TIMEOUT", "300"))
USAGE_LOG = Path(os.environ.get("DATA_DIR", "/data")) / "vlm_usage.jsonl"

_log_lock = threading.Lock()


class RelayError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def prepare(body: dict) -> dict:
    """检查并整理转发给 OpenRouter 的请求体（纯函数，便于测试）。"""
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body["messages"]:
        raise RelayError(400, "请求里没有 messages")
    model = body.get("model") or MODELS[0]
    if model not in MODELS:
        raise RelayError(403, f"模型 {model} 不在白名单里（允许：{', '.join(MODELS)}）")
    out = dict(body)
    out["model"] = model
    mt = out.get("max_tokens")
    if not isinstance(mt, int) or mt <= 0 or mt > MAX_TOKENS:
        out["max_tokens"] = MAX_TOKENS
    out["stream"] = False
    out["usage"] = {"include": True}       # 让 OpenRouter 在返回里带上实际花费
    return out


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        raise RelayError(503, "douyin-editor 还没配置 OPENROUTER_API_KEY")
    return k


def _record(model: str, usage: dict | None, seconds: float, status: int) -> None:
    usage = usage or {}
    row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, "status": status,
           "seconds": round(seconds, 1), "prompt_tokens": usage.get("prompt_tokens"),
           "completion_tokens": usage.get("completion_tokens"), "cost_usd": usage.get("cost")}
    try:
        with _log_lock, USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def usage_summary(since: float = 0.0) -> dict:
    """汇总 vlm_usage.jsonl：调用次数、token、美元花费。since 是时间戳（秒）。"""
    calls = cost = pt = ct = 0
    if USAGE_LOG.exists():
        for line in USAGE_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(line)
                if time.mktime(time.strptime(r["t"], "%Y-%m-%d %H:%M:%S")) < since:
                    continue
            except (ValueError, KeyError):
                continue
            calls += 1
            cost += r.get("cost_usd") or 0
            pt += r.get("prompt_tokens") or 0
            ct += r.get("completion_tokens") or 0
    return {"calls": calls, "prompt_tokens": pt, "completion_tokens": ct, "cost_usd": round(cost, 5)}


def forward(body: dict, opener=urllib.request.urlopen) -> tuple[int, bytes]:
    out = prepare(body)
    req = urllib.request.Request(API_BASE + "/chat/completions", data=json.dumps(out).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {_key()}",
                                          "X-Title": "rea-video via douyin-editor"})
    t0 = time.time()
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            status, data = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, data = e.code, e.read()
    usage = None
    try:
        usage = json.loads(data).get("usage")
    except (ValueError, AttributeError):
        pass
    _record(out["model"], usage, time.time() - t0, status)
    return status, data


class _Handler(BaseHTTPRequestHandler):
    server_version = "vlm-relay"

    def _send(self, status: int, payload: bytes | dict) -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            return self._send(200, {"data": [{"id": m, "object": "model"} for m in MODELS]})
        if self.path.rstrip("/") == "/usage":
            return self._send(200, usage_summary())
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": {"message": "not found"}})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                raise RelayError(413, f"请求体大小不对（上限 {MAX_BODY // 1024 // 1024}MB）")
            body = json.loads(self.rfile.read(n))
            status, data = forward(body)
            self._send(status, data)
        except RelayError as e:
            self._send(e.status, {"error": {"message": e.message}})
        except ValueError:
            self._send(400, {"error": {"message": "请求不是合法 JSON"}})
        except Exception as e:  # noqa: BLE001  转发失败不能拖垮剪辑服务
            self._send(502, {"error": {"message": f"转发失败：{type(e).__name__}"}})

    def log_message(self, fmt, *args):  # 不把请求内容打进日志
        pass


def start() -> ThreadingHTTPServer | None:
    """在后台线程启动转发服务；端口被占用时只打印提示，不影响剪辑服务。"""
    try:
        srv = ThreadingHTTPServer((HOST, PORT), _Handler)
    except OSError as e:
        print(f"看图转发没启动（{HOST}:{PORT}）：{e}")
        return None
    threading.Thread(target=srv.serve_forever, name="vlm-relay", daemon=True).start()
    print(f"看图转发: http://{HOST}:{PORT}/v1  模型 {', '.join(MODELS)}")
    return srv
