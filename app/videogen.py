"""AI 生成视频：调用 OpenRouter 视频接口（文生视频 / 图生视频），生成后直接导入视频库。

流程：POST /videos 提交 → 轮询 /videos/{id} → 下载 /videos/{id}/content → 存成 video_id，
之后可以像导入的原片一样用在 render 的 clips 里（clips 里写 video_id 就能和别的视频拼在一起）。
密钥和配音共用 .env 里的 OPENROUTER_API_KEY。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import requests

import editor
from editor import EditorError
from tts import API_BASE, _key

DEFAULT_MODEL = os.environ.get("OPENROUTER_VIDEO_MODEL", "google/veo-3.1")
TIMEOUT = int(os.environ.get("VIDEO_GEN_TIMEOUT", "1800"))
POLL = 10


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_key()}",
            "HTTP-Referer": os.environ.get("PUBLIC_URL", "http://localhost"),
            "X-Title": "douyin-editor"}


def _mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise EditorError("参考图不是 PNG / JPEG / WebP 图片")


def _image_ref(url: str) -> dict[str, Any]:
    """普通图片直链原样传给接口；Google Drive 链接先下载到服务器，再以 data URL 传过去
    （视频服务商拿不到 Drive 分享页里的图片）。"""
    if "drive.google.com" not in url and "usercontent" not in url:
        return {"type": "image_url", "image_url": {"url": url}}
    tmp = Path(tempfile.mkdtemp(prefix="ref_", dir=editor.DATA_DIR))
    try:
        data = editor.download(url, tmp).read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{_mime(data)};base64,{b64}"}}


def list_models(filter_text: str | None = None) -> list[dict[str, Any]]:
    r = requests.get(f"{API_BASE}/videos/models", headers=_headers(), timeout=60)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("data", payload if isinstance(payload, list) else [])
    out = []
    for m in items:
        text = json.dumps(m, ensure_ascii=False)
        if filter_text and filter_text.lower() not in text.lower():
            continue
        out.append({k: m.get(k) for k in (
            "id", "name", "supported_durations", "supported_resolutions",
            "supported_aspect_ratios", "pricing_skus") if k in m} or m)
    return out


def generate(prompt: str, model: str | None = None, image_url: str | None = None,
             last_image_url: str | None = None, reference_urls: list[str] | None = None,
             duration: int | None = None, resolution: str | None = None,
             aspect_ratio: str | None = "9:16", generate_audio: bool = False,
             seed: int | None = None, name: str | None = None,
             progress=lambda msg: None) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        raise EditorError("prompt 不能为空")
    model = model or DEFAULT_MODEL
    body: dict[str, Any] = {"model": model, "prompt": prompt.strip(),
                            "generate_audio": bool(generate_audio)}
    if duration:
        body["duration"] = int(duration)
    if resolution:
        body["resolution"] = resolution
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if seed is not None:
        body["seed"] = int(seed)
    frames = []
    if image_url:
        progress("准备首帧图")
        frames.append({**_image_ref(image_url), "frame_type": "first_frame"})
    if last_image_url:
        frames.append({**_image_ref(last_image_url), "frame_type": "last_frame"})
    if frames:
        body["frame_images"] = frames
    elif reference_urls:
        progress("准备参考图")
        body["input_references"] = [_image_ref(u) for u in reference_urls[:4]]

    progress("提交生成任务")
    r = requests.post(f"{API_BASE}/videos", json=body, headers=_headers(), timeout=120)
    if r.status_code >= 400:
        raise EditorError(f"提交失败 HTTP {r.status_code}：{r.text[:800]}")
    job = r.json()
    gid = job.get("id")
    if not gid:
        raise EditorError(f"接口没返回任务 id：{str(job)[:500]}")

    t0 = time.time()
    status = job.get("status", "pending")
    while status not in ("completed", "failed", "cancelled", "expired"):
        if time.time() - t0 > TIMEOUT:
            raise EditorError(f"生成超时（{TIMEOUT} 秒），任务 id {gid}，稍后可在 OpenRouter 后台查看")
        time.sleep(POLL)
        try:
            pr = requests.get(f"{API_BASE}/videos/{gid}", headers=_headers(), timeout=60)
            if pr.status_code < 500:
                job = pr.json()
                status = job.get("status", status)
        except (requests.RequestException, ValueError):
            pass  # 偶发网络问题，下一轮再查
        progress(f"生成中（{status}，已等 {int(time.time() - t0)} 秒）")
    if status != "completed":
        raise EditorError(f"生成失败（{status}）：{str(job.get('error') or job)[:800]}")

    progress("下载视频")
    vid = uuid.uuid4().hex[:12]
    d = editor.VIDEOS / vid
    d.mkdir(parents=True)
    try:
        src = d / "source.mp4"
        with requests.get(f"{API_BASE}/videos/{gid}/content", params={"index": 0},
                          headers=_headers(), stream=True, timeout=600) as dr:
            if dr.status_code >= 400:
                raise EditorError(f"下载失败 HTTP {dr.status_code}：{dr.text[:500]}")
            editor._stream_to(dr, src)
        info = editor.probe(src)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    meta = {"video_id": vid, "name": name or f"AI生成·{prompt.strip()[:20]}", "url": "",
            "source": src.name, **info,
            "generated": {"model": model, "prompt": prompt.strip(), "job_id": gid,
                          "cost": (job.get("usage") or {}).get("cost"),
                          "seconds": round(time.time() - t0, 1)}}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta
