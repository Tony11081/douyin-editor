"""HeyGen 数字人口播：用你在 HeyGen 里的数字人（或照片数字人）和音色，按文案生成口播视频，
完成后自动导入视频库，之后就是普通口播素材：transcribe → render 精剪、字幕、BGM。

密钥放在服务器 .env 的 HEYGEN_API_KEY，不经过对话。
接口：GET /v2/avatars、GET /v2/voices、POST /v2/video/generate、GET /v1/video_status.get
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from typing import Any

import requests

import editor
from editor import EditorError

API = os.environ.get("HEYGEN_BASE_URL", "https://api.heygen.com").rstrip("/")
TIMEOUT = int(os.environ.get("HEYGEN_TIMEOUT", "3600"))
POLL = 10
MAX_SCRIPT = 1500  # HeyGen 单段文案上限


def _headers() -> dict[str, str]:
    k = os.environ.get("HEYGEN_API_KEY", "").strip()
    if not k:
        raise EditorError("服务器还没配置 HEYGEN_API_KEY：在 .env 里加一行 HEYGEN_API_KEY=...，"
                          "然后 systemctl restart douyin-editor")
    return {"X-Api-Key": k, "Accept": "application/json"}


def _get(path: str, **params) -> dict[str, Any]:
    r = requests.get(f"{API}{path}", headers=_headers(), params=params or None, timeout=60)
    if r.status_code >= 400:
        raise EditorError(f"HeyGen 接口出错 {path} HTTP {r.status_code}：{r.text[:500]}")
    return r.json()


def _match(text: str, f: str | None) -> bool:
    return not f or f.lower() in text.lower()


def list_avatars(filter_text: str | None = None) -> dict[str, Any]:
    """列出账号里能用的数字人（含照片数字人）。公共形象很多，建议用 filter_text 按名字搜你的数字人。"""
    data = _get("/v2/avatars").get("data", {})
    avatars = [{"avatar_id": a.get("avatar_id"), "name": a.get("avatar_name"), "gender": a.get("gender"),
                "type": a.get("type"), "premium": a.get("premium"),
                "preview_image_url": a.get("preview_image_url")}
               for a in data.get("avatars", [])
               if _match(f"{a.get('avatar_id')} {a.get('avatar_name', '')}", filter_text)]
    photos = [{"talking_photo_id": p.get("talking_photo_id"), "name": p.get("talking_photo_name"),
               "preview_image_url": p.get("preview_image_url")}
              for p in data.get("talking_photos", [])
              if _match(f"{p.get('talking_photo_id')} {p.get('talking_photo_name', '')}", filter_text)]
    return {"avatar_count": len(avatars), "avatars": avatars[:60],
            "talking_photo_count": len(photos), "talking_photos": photos[:60]}


def list_voices(filter_text: str | None = None, language: str | None = "Chinese") -> list[dict[str, Any]]:
    try:
        voices = _get("/v2/voices").get("data", {}).get("voices", [])
    except EditorError:
        voices = _get("/v1/voice.list").get("data", {}).get("list", [])
    out = []
    for v in voices:
        lang = v.get("language", "") or ""
        text = f"{v.get('voice_id')} {v.get('name', v.get('display_name', ''))} {lang}"
        if language and language.lower() not in lang.lower() and not filter_text:
            continue
        if _match(text, filter_text):
            out.append({"voice_id": v.get("voice_id"), "name": v.get("name") or v.get("display_name"),
                        "language": lang, "gender": v.get("gender"),
                        "preview_audio": v.get("preview_audio")})
    return out[:80]


def _background(bg: str | None) -> dict[str, Any] | None:
    if not bg:
        return None
    if bg.startswith("#"):
        return {"type": "color", "value": bg}
    if bg.startswith("http"):
        kind = "video" if bg.split("?")[0].lower().endswith((".mp4", ".mov", ".webm")) else "image"
        return {"type": kind, "url": bg, **({"play_style": "loop"} if kind == "video" else {})}
    raise EditorError("background 需要是 #RRGGBB 颜色，或图片/视频直链")


def generate(script: str, avatar_id: str | None = None, talking_photo_id: str | None = None,
             voice_id: str | None = None, speed: float = 1.0, aspect_ratio: str = "9:16",
             background: str | None = None, avatar_style: str = "normal", test: bool = False,
             title: str | None = None, name: str | None = None,
             progress=lambda msg: None) -> dict[str, Any]:
    script = (script or "").strip()
    if not script:
        raise EditorError("口播文案不能为空")
    if len(script) > MAX_SCRIPT:
        raise EditorError(f"文案 {len(script)} 字，超过 HeyGen 单段上限 {MAX_SCRIPT} 字，请分段生成")
    if bool(avatar_id) == bool(talking_photo_id):
        raise EditorError("avatar_id 和 talking_photo_id 二选一（用 heygen_avatars 查）")
    if not voice_id:
        raise EditorError("需要 voice_id（用 heygen_voices 查你的音色）")
    character = ({"type": "avatar", "avatar_id": avatar_id, "avatar_style": avatar_style}
                 if avatar_id else {"type": "talking_photo", "talking_photo_id": talking_photo_id})
    item: dict[str, Any] = {"character": character,
                            "voice": {"type": "text", "input_text": script, "voice_id": voice_id,
                                      "speed": float(speed)}}
    bg = _background(background)
    if bg:
        item["background"] = bg
    body: dict[str, Any] = {"video_inputs": [item], "test": bool(test)}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if title:
        body["title"] = title
    progress("提交数字人视频")
    r = requests.post(f"{API}/v2/video/generate", json=body,
                      headers={**_headers(), "Content-Type": "application/json"}, timeout=120)
    if r.status_code >= 400:
        raise EditorError(f"提交失败 HTTP {r.status_code}：{r.text[:800]}")
    js = r.json()
    hid = (js.get("data") or {}).get("video_id")
    if not hid:
        raise EditorError(f"HeyGen 没返回 video_id：{str(js)[:500]}")

    t0 = time.time()
    data: dict[str, Any] = {}
    status = "pending"
    while status not in ("completed", "failed"):
        if time.time() - t0 > TIMEOUT:
            raise EditorError(f"等待超时（{TIMEOUT} 秒），HeyGen 视频 id {hid}，可稍后在 HeyGen 后台下载")
        time.sleep(POLL)
        try:
            data = _get("/v1/video_status.get", video_id=hid).get("data", {}) or {}
            status = data.get("status", status)
        except (EditorError, requests.RequestException, ValueError):
            pass
        progress(f"数字人生成中（{status}，已等 {int(time.time() - t0)} 秒）")
    if status != "completed" or not data.get("video_url"):
        raise EditorError(f"HeyGen 生成失败：{str(data.get('error') or data)[:800]}")

    progress("下载数字人视频")
    vid = uuid.uuid4().hex[:12]
    d = editor.VIDEOS / vid
    d.mkdir(parents=True)
    try:
        src = d / "source.mp4"
        with requests.get(data["video_url"], stream=True, timeout=600) as dr:
            dr.raise_for_status()
            editor._stream_to(dr, src)
        info = editor.probe(src)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    meta = {"video_id": vid, "name": name or f"数字人·{script[:16]}", "url": "", "source": src.name,
            **info, "heygen": {"video_id": hid, "avatar_id": avatar_id,
                               "talking_photo_id": talking_photo_id, "voice_id": voice_id,
                               "script": script, "test": bool(test),
                               "seconds": round(time.time() - t0, 1)}}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta
