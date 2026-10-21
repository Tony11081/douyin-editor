"""抖音口播剪辑 MCP 服务：给 Claude 用的远程剪辑工具。"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import sys
from pathlib import Path

import uvicorn
from mcp.server.mcpserver import Image, MCPServer
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor  # noqa: E402
import tts  # noqa: E402
import videogen  # noqa: E402
import heygen  # noqa: E402

TOKEN = os.environ.get("ACCESS_TOKEN", "")
if len(TOKEN) < 16:
    raise SystemExit("请在 .env 里设置 ACCESS_TOKEN（至少 16 位随机字符）")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
PORT = int(os.environ.get("PORT", "8000"))

INSTRUCTIONS = """抖音口播剪辑工具。典型流程：
1. import_video(url) 导入（支持公开的 Google Drive 文件/文件夹链接或直链）→ wait_job
2. transcribe(video_id) → wait_job，拿到逐句+逐字时间
3. 根据逐字时间决定保留哪些片段（去口误、重复、停顿，可重排，把钩子句放最前）
4. render(spec) → wait_job，拿到成片下载链接
5. get_frames 看几帧检查字幕和构图，有问题改 spec 重新 render
没有人声的视频（动画、素材混剪）可以用 AI 配音：
a. tts(segments=[逐句旁白]) → wait_job，拿到 tts_id 和每句时长（可先 tts_voices 选模型/音色）
b. 按每句时长安排画面，render 时加 voiceover={tts_id, at:[每句开始秒数]}，字幕自动按配音生成
AI 生成视频：generate_video(prompt, image_url?) → wait_job（通常几分钟），得到新的 video_id；
render 的 clips 里每段可写自己的 video_id，把多个生成镜头和原片拼成一条成片。
画面已经做好（例如 Claude 本地渲染的动画）：import_video(成片链接) → tts → mux，
mux 只合成声音，画面原样复制、不重新编码。
数字人口播：heygen_avatars / heygen_voices 找到数字人和音色 → heygen_avatar_video(文案) → wait_job
→ 得到 video_id，之后按普通口播走 transcribe → render（精剪、字幕、标题、BGM）。
耗时操作都返回 job_id，用 wait_job 轮询。"""

mcp = MCPServer(name="douyin-editor", title="抖音口播剪辑", instructions=INSTRUCTIONS)

# ---------------------------------------------------------------- 后台任务
_heavy = ThreadPoolExecutor(max_workers=int(os.environ.get("RENDER_WORKERS", "1")))
_light = ThreadPoolExecutor(max_workers=3)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _submit(kind: str, fn, *args, heavy: bool = True) -> str:
    jid = f"{kind}-{uuid.uuid4().hex[:10]}"
    job = {"job_id": jid, "kind": kind, "state": "queued", "progress": "排队中",
           "created": time.time(), "result": None, "error": None}
    with _lock:
        _jobs[jid] = job

    def progress(msg: str) -> None:
        job["progress"] = msg

    def runner():
        if job.get("cancel"):
            job["state"] = "cancelled"
            job["progress"] = "已取消"
            job["finished"] = time.time()
            return
        job["state"] = "running"
        job["progress"] = "处理中"
        try:
            job["result"] = fn(*args, progress=progress) if kind in ("render", "genvideo", "avatar") \
                else fn(*args)
            job["state"] = "done"
            job["progress"] = "完成"
        except Exception as e:  # noqa: BLE001
            job["state"] = "error"
            job["error"] = str(e) if isinstance(e, editor.EditorError) else \
                f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        job["finished"] = time.time()

    (_heavy if heavy else _light).submit(runner)
    return jid


def _file_url(name: str) -> str:
    return f"{PUBLIC_URL}/files/{TOKEN}/{name}"


def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    v = {k: job[k] for k in ("job_id", "kind", "state", "progress")}
    if job.get("finished"):
        v["seconds"] = round(job["finished"] - job["created"], 1)
    if job["state"] == "error":
        v["error"] = job["error"]
    if job["state"] == "done":
        r = job["result"]
        if job["kind"] == "transcribe":
            v["transcript"] = editor.transcript_text(r)
        elif job["kind"] == "render":
            v["result"] = {**r, "download_url": _file_url(r["file"])}
        elif job["kind"] == "tts":
            v["result"] = _tts_view(r)
        else:
            v["result"] = r
    return v


def _tts_view(meta: dict[str, Any]) -> dict[str, Any]:
    return {"tts_id": meta["tts_id"], "model": meta["model"], "voice": meta["voice"],
            "total": meta["total"], "gap": meta["gap"],
            "segments": [{k: it[k] for k in ("index", "text", "duration", "start", "end")}
                         for it in meta["segments"]],
            "preview_url": f"{PUBLIC_URL}/files/{TOKEN}/tts/{meta['tts_id']}.mp3"}


# ---------------------------------------------------------------- 工具
@mcp.tool()
def import_video(url: str, name: str | None = None) -> dict:
    """导入一个视频。url 可以是 Google Drive 文件分享链接（需设为「知道链接的任何人可查看」）
    或任何视频直链。返回 job_id，用 wait_job 等结果（含 video_id、时长、分辨率）。"""
    return {"job_id": _submit("import", editor.import_video, url, name, heavy=False)}


@mcp.tool()
def list_drive_folder(url: str) -> list[dict]:
    """列出公开 Google Drive 文件夹里的文件（名称 + 链接），再逐个 import_video。"""
    return editor.list_drive_folder(url)


@mcp.tool()
def list_videos() -> list[dict]:
    """列出服务器上已导入的视频。"""
    out = []
    for d in sorted(editor.VIDEOS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        m = d / "meta.json"
        if m.exists():
            meta = json.loads(m.read_text())
            out.append({k: meta.get(k) for k in ("video_id", "name", "duration", "width", "height")}
                       | {"transcribed": (d / "transcript.json").exists()})
    return out


@mcp.tool()
def transcribe(video_id: str, language: str = "zh") -> dict:
    """语音转文字（Whisper），得到逐句和逐字时间戳，用来精确决定剪辑点。返回 job_id。"""
    editor.video_dir(video_id)
    return {"job_id": _submit("transcribe", editor.transcribe, video_id, language)}


@mcp.tool()
def get_transcript(video_id: str) -> str:
    """读取已有的转写结果（格式：S序号 [开始-结束] 句子，下一行是逐字时间）。"""
    tr = editor.load_transcript(video_id)
    if not tr:
        return "还没有转写，请先调用 transcribe"
    return editor.transcript_text(tr)


@mcp.tool()
def render(spec: dict) -> dict:
    """按剪辑方案渲染抖音竖屏成片，返回 job_id；wait_job 完成后给出 download_url 和实际字幕列表。

    spec 字段（时间都是原视频的秒数）：
    - video_id（必填）
    - clips: [{start, end, zoom?=1.0, text?, focus_y?}] 按成片顺序排列，可重排。
        zoom 如 1.12 表示该片段推近（跳切推镜头）。text 是该片段的正确字幕文字（可选；
        不填就用转写的字自动生成）。
    - captions: "auto"（默认）或 "none"
    - corrections: {"错字": "正确"} 自动字幕时的错字替换，例如 {"yellow88": "1688"}
    - highlight_words: ["便宜", "百分百"] 字幕里标黄的重点词
    - caption_style: {font_size?, y?=0.68（字幕底边所在高度比例）, max_chars?=12,
        color?="#FFFFFF", highlight_color?="#FFD400", outline?, font?}
    - title: {text, duration?（秒，不填=全程）, y?=0.12, box_color?="#E6312E"} 顶部标题条
    - bgm: {name（list_music 里的文件名）或 url, volume?=0.12, fade_in?=0.5, fade_out?=1.5}
        人声出现时 BGM 自动压低。
    - audio: {denoise?=true, loudnorm?=true}
    - voiceover: {tts_id, at?: [每句在成片里的开始秒数，数量和配音句数一致；不填按配音顺排],
        volume?=1.0, original_volume?=0（原片声音保留多少，0 = 只要配音）}
        有 voiceover 且原片没转写时，字幕自动按配音文字生成；也可 captions: "voiceover" 强制使用。
    - width?=1080, height?=1920, fps?=30, focus_y?=0.35（裁切时人脸偏上的位置）
    """
    if "video_id" not in spec:
        raise ValueError("spec 缺少 video_id")
    editor.video_dir(spec["video_id"])
    return {"job_id": _submit("render", editor.render, json.loads(json.dumps(spec)))}


@mcp.tool()
def tts(segments: list[str], model: str | None = None, voice: str | None = None,
        instructions: str | None = None, speed: float | None = None,
        gap: float = 0.3) -> dict:
    """AI 配音（OpenRouter 语音接口）。segments 是逐句旁白（建议一句一个镜头），
    每句单独生成并去掉首尾静音，wait_job 完成后返回 tts_id、每句时长和试听链接 preview_url。
    - model：默认用服务器 .env 的 OPENROUTER_TTS_MODEL；可用 tts_voices 查模型
    - voice：音色 ID（随模型不同，例如 OpenAI 的 alloy、nova）
    - instructions：语气说明，如「沉稳的知识类讲解，语速稍快」（OpenAI / Gemini / Fish Audio 支持）
    - speed：语速倍率（部分模型支持）；gap：顺排时句与句的间隔秒数
    数字、百分号建议写成汉字读法（如「百分之二」），字幕里再用 corrections 改回「2%」。"""
    if not isinstance(segments, list) or not segments:
        raise ValueError("segments 需要是非空的句子列表")
    return {"job_id": _submit("tts", tts.synthesize, segments, model, voice, instructions,
                              speed, gap, heavy=False)}


@mcp.tool()
def tts_voices(filter_text: str | None = None) -> list[dict]:
    """列出 OpenRouter 上的语音模型（含价格、可用音色 supported_voices）。filter_text 可按名称过滤，如 seed、fish。"""
    return tts.list_voices(filter_text)


@mcp.tool()
def get_tts(tts_id: str) -> dict:
    """查看一次配音的每句文字、时长和试听链接。"""
    return _tts_view(tts.load(tts_id))


@mcp.tool()
def generate_video(prompt: str, model: str | None = None, image_url: str | None = None,
                   last_image_url: str | None = None, reference_urls: list[str] | None = None,
                   duration: int | None = None, resolution: str | None = None,
                   aspect_ratio: str | None = "9:16", generate_audio: bool = False,
                   seed: int | None = None, name: str | None = None) -> dict:
    """AI 生成视频（OpenRouter 视频接口），完成后自动导入视频库，返回 video_id。返回 job_id，
    用 wait_job 反复等待（生成通常要 1~5 分钟）。
    - prompt：画面描述（主体、动作、镜头运动、光线、风格），建议写清楚「镜头缓慢推进」等运镜
    - image_url：首帧图（图生视频，让插画动起来）；last_image_url：尾帧图。
      支持图片直链或 Google Drive 分享链接（需「知道链接的任何人可查看」）
    - reference_urls：风格/内容参考图（没有首帧图时生效）
    - duration / resolution / aspect_ratio：要符合模型支持的值（video_models 可查），默认竖屏 9:16
    - generate_audio：是否让模型生成环境音（默认关，配音和 BGM 另外加）
    - model：默认用 .env 的 OPENROUTER_VIDEO_MODEL
    生成的视频按秒计费，较贵：先用短时长、低分辨率试，满意再出正式版。"""
    return {"job_id": _submit("genvideo", videogen.generate, prompt, model, image_url,
                              last_image_url, reference_urls, duration, resolution,
                              aspect_ratio, generate_audio, seed, name, heavy=False)}


@mcp.tool()
def video_models(filter_text: str | None = None) -> list[dict]:
    """列出 OpenRouter 上的视频生成模型，以及各自支持的时长、分辨率、画幅和价格。"""
    return videogen.list_models(filter_text)


@mcp.tool()
def mux(spec: dict) -> dict:
    """只混音、不动画面：视频画面原样复制（不重新编码、不加任何特效/字幕），
    只把 AI 配音和背景音乐合进去。用于画面已经做好的成片（例如 Claude 用代码渲染的动画）。
    返回 job_id；wait_job 完成后给出 download_url。
    spec 字段：
    - video_id（必填）：先用 import_video 导入做好的成片
    - voiceover: {tts_id, at?: [每句开始秒数], volume?=1.0}
    - bgm: {name 或 url, volume?=0.12, fade_in?=0.5, fade_out?=1.5, start?=0}，有配音时自动避让
    - original_volume?=0：成片原有声音保留多少；loudnorm?=true"""
    if "video_id" not in spec:
        raise ValueError("spec 缺少 video_id")
    editor.video_dir(spec["video_id"])
    return {"job_id": _submit("render", editor.mux, json.loads(json.dumps(spec)))}


@mcp.tool()
def heygen_avatars(filter_text: str | None = None) -> dict:
    """列出 HeyGen 账号里的数字人（avatar_id）和照片数字人（talking_photo_id）。
    公共形象很多，用 filter_text 按名字搜用户自己的数字人。"""
    return heygen.list_avatars(filter_text)


@mcp.tool()
def heygen_voices(filter_text: str | None = None, language: str | None = "Chinese") -> list[dict]:
    """列出 HeyGen 音色（含用户克隆的声音），默认只看中文；filter_text 可按名字搜。"""
    return heygen.list_voices(filter_text, language)


@mcp.tool()
def heygen_avatar_video(script: str, voice_id: str, avatar_id: str | None = None,
                        talking_photo_id: str | None = None, speed: float = 1.0,
                        aspect_ratio: str = "9:16", background: str | None = None,
                        avatar_style: str = "normal", test: bool = False,
                        title: str | None = None, name: str | None = None) -> dict:
    """用 HeyGen 数字人按文案生成口播视频，完成后自动导入视频库，返回 video_id。返回 job_id，
    用 wait_job 反复等待（通常几分钟，长文案更久）。
    - script：口播文案（单段 ≤1500 字）；数字建议写成汉字读法
    - avatar_id 或 talking_photo_id 二选一；voice_id 用 heygen_voices 查（可用用户自己克隆的声音）
    - background：#00FF00 这类纯色（方便后期抠像），或图片/视频直链
    - test=True：HeyGen 测试模式（带水印、不扣额度），先试效果用
    生成后：transcribe(video_id) → render 精剪、加字幕和 BGM。"""
    return {"job_id": _submit("avatar", heygen.generate, script, avatar_id, talking_photo_id,
                              voice_id, speed, aspect_ratio, background, avatar_style, test,
                              title, name, heavy=False)}


@mcp.tool()
def wait_job(job_id: str, wait_seconds: int = 50) -> dict:
    """等待任务完成（最多 wait_seconds 秒，上限 55）。state 为 queued/running 时再次调用即可。"""
    job = _jobs.get(job_id)
    if not job:
        raise ValueError("找不到这个 job_id（服务重启后任务会丢失）")
    end = time.time() + max(0, min(int(wait_seconds), 55))
    while job["state"] in ("queued", "running") and time.time() < end:
        time.sleep(1)
    return _job_view(job)


@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """取消还在排队的任务（已经开始运行的任务无法中途停止）。"""
    job = _jobs.get(job_id)
    if not job:
        raise ValueError("找不到这个 job_id")
    if job["state"] == "queued":
        job["cancel"] = True
        return {"job_id": job_id, "cancelled": True}
    return {"job_id": job_id, "cancelled": False, "state": job["state"]}


@mcp.tool()
def list_jobs() -> list[dict]:
    """列出最近的任务和状态（排队中/运行中/完成/出错）。"""
    jobs = sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)[:20]
    return [{k: j[k] for k in ("job_id", "kind", "state", "progress")} for j in jobs]


@mcp.tool()
def get_frames(times: list[float], output_id: str | None = None,
               video_id: str | None = None, width: int = 360) -> list[Image]:
    """截取成片（output_id）或原片（video_id）在指定秒数的画面，用来检查字幕、构图、推镜头。最多 8 张。"""
    if output_id:
        data = editor.frames("output", output_id, times, width)
    elif video_id:
        data = editor.frames("video", video_id, times, width)
    else:
        raise ValueError("需要 output_id 或 video_id")
    return [Image(data=b, format="jpeg") for b in data]


@mcp.tool()
def list_music() -> list[str]:
    """列出服务器音乐库里的背景音乐文件（放在 data/music 目录）。"""
    return sorted(p.name for p in editor.MUSIC.iterdir() if p.is_file() and not p.name.startswith("."))


@mcp.tool()
def find_music(page_url: str, keyword: str | None = None) -> list[dict]:
    """抓取曲库网页（例如 https://mixkit.co/free-stock-music/mood/positive/ ），列出页面里的
    mp3 链接，再用 add_music 下载。keyword 可按文件名过滤。"""
    return editor.find_audio_links(page_url, keyword)


@mcp.tool()
def add_music(url: str, name: str) -> dict:
    """从链接下载一首背景音乐到音乐库（Drive 公开链接或直链）。返回 job_id。"""
    return {"job_id": _submit("music", editor.import_music, url, name, heavy=False)}


@mcp.tool()
def list_outputs() -> list[dict]:
    """列出已渲染的成片和下载链接。"""
    out = []
    for p in sorted(editor.OUTPUTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        r = json.loads(p.read_text())
        out.append({"output_id": r["output_id"], "video_id": r["spec"]["video_id"],
                    "duration": r["duration"], "download_url": _file_url(r["file"])})
    return out


# ---------------------------------------------------------------- HTTP 路由
@mcp.custom_route("/files/{token}/{name}", methods=["GET", "HEAD"], include_in_schema=False)
async def files(request: Request):
    tok, name = request.path_params["token"], request.path_params["name"]
    if not secrets.compare_digest(tok, TOKEN) or not re.fullmatch(r"[a-z0-9]{12}\.mp4", name):
        return PlainTextResponse("not found", status_code=404)
    path = editor.OUTPUTS / name
    if not path.exists():
        return PlainTextResponse("not found", status_code=404)
    return FileResponse(path, media_type="video/mp4", filename=f"douyin_{name}")


@mcp.custom_route("/files/{token}/tts/{name}", methods=["GET", "HEAD"], include_in_schema=False)
async def tts_files(request: Request):
    tok, name = request.path_params["token"], request.path_params["name"]
    m = re.fullmatch(r"([a-z0-9]{12})\.mp3", name)
    if not secrets.compare_digest(tok, TOKEN) or not m:
        return PlainTextResponse("not found", status_code=404)
    try:
        path = tts.preview(m.group(1))
    except editor.EditorError:
        return PlainTextResponse("not found", status_code=404)
    return FileResponse(path, media_type="audio/mpeg", filename=f"voice_{name}")


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_: Request):
    return JSONResponse({"ok": True})


app = mcp.streamable_http_app(streamable_http_path=f"/mcp/{TOKEN}", stateless_http=True,
                              json_response=True, host="0.0.0.0")

if __name__ == "__main__":
    print(f"MCP 地址: {PUBLIC_URL}/mcp/{TOKEN}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
