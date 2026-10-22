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
import tts as tts_mod  # noqa: E402  不能叫 tts：会被下面同名的 tts() 工具函数覆盖
import videogen  # noqa: E402
import heygen  # noqa: E402
import webrec  # noqa: E402

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
网站功能演示（口播 + 真实录屏）：record_web(url, steps) → wait_job 得到录屏 video_id 和每一步的秒数 marks；
再 render，clips 里口播片段和录屏片段（写各自 video_id）按口播内容穿插，口播声音在录屏段里照常保留
（录屏没有声音，字幕按口播自动生成）。录屏可先 get_frames 看几帧确认页面和点击位置。
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
            job["result"] = fn(*args, progress=progress) if kind in ("render", "genvideo", "avatar", "record") \
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
            "preview_url": f"{PUBLIC_URL}/files/{TOKEN}/tts/{meta['tts_id']}.mp3",
            "verify": meta.get("verify")}


# ---------------------------------------------------------------- 工具
@mcp.tool()
def import_video(url: str, name: str | None = None) -> dict:
    """导入一个视频。url 可以是 Google Drive 文件分享链接（需设为「知道链接的任何人可查看」）
    或任何视频直链。返回 job_id，用 wait_job 等结果（含 video_id、时长、分辨率）。
    也可以录网站：url 写成 record:{"url": "...", "steps": [...], "layout"?, "settle"?, "cursor"?}
    （JSON，参数和 record_web 完全一样），效果等同 record_web，结果里带 marks。"""
    if url.startswith("record:"):
        try:
            a = json.loads(url[len("record:"):])
        except ValueError as e:
            raise ValueError(f"record: 后面要跟 JSON：{e}") from e
        if not isinstance(a, dict) or "url" not in a:
            raise ValueError('record: 的 JSON 需要 {"url": ..., "steps": [...]}')
        return {"job_id": _submit("record", webrec.record, a["url"], a.get("steps"), name,
                                  a.get("layout", "mobile"), a.get("settle", 0.8), a.get("cursor", True),
                                  heavy=False)}
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
    - title: {text, duration?（秒，不填=全程）, y?=0.085, font_size?, color?, color2?, outline_color?}
        顶部大标题（第一行 color，第二行起 color2）
    - bgm: {name（list_music 里的文件名）或 url, volume?=0.12, fade_in?=0.5, fade_out?=1.5}
        人声出现时 BGM 自动压低。
    - audio: {denoise?=true, loudnorm?=true}
    - voiceover: {tts_id, at?: [每句在成片里的开始秒数，数量和配音句数一致；不填按配音顺排],
        volume?=1.0, original_volume?=0（原片声音保留多少，0 = 只要配音）}
        有 voiceover 且原片没转写时，字幕自动按配音文字生成；也可 captions: "voiceover" 强制使用。
    - effects: {drift?=0.04（缓慢推拉，0 关闭）, flash_first?=true, sfx?=true（转场音效）,
        progress_bar?=true, bar_color?, bar_height?} —— 不写就用默认值，结果的 applied 会列出来
    - overlays: [{video_id 或 url, start（成片第几秒开始）, from?（取来源第几秒起）, duration?（叠加几秒）,
        x?=0, y?=0, w?/h?（缩放到的像素）, fade?（淡入淡出秒数）, layer?="front"}]
        layer："base" 在字幕之下盖住画面（网站录屏整幅铺满时用：口播声音和字幕照常），
        "front" 在字幕之上（透明动画、小窗），"behind" 在人物后面（自动抠像）。
        url 是透明 VP9 webm 或任意视频直链；video_id 是视频库里的视频（例如 record_web 的录屏）。
    - width?=1080, height?=1920, fps?=30, focus_y?=0.35（裁切时人脸偏上的位置）
    - shift_y?：分屏模板用，整幅画面下移多少像素（上方补 shift_color，默认 #F4F3EC），人物落到下半屏
    严格模式：写错的参数名、类型、超出范围的值、超出视频时长的片段都会直接报错，不会被忽略或偷偷改。
    建议先用 validate_spec 预演，确认时间线、字幕、配音位置无误再 render。
    完成结果里 checks 是成片自检（分辨率、帧率、时长、每句配音有声、响度），warnings 是需要留意的地方。
    """
    spec = json.loads(json.dumps(spec))
    editor.plan_render(json.loads(json.dumps(spec)))  # 先同步校验，有问题马上报错
    return {"job_id": _submit("render", editor.render, spec)}


@mcp.tool()
def validate_spec(spec: dict) -> dict:
    """预演 render：严格校验剪辑方案，返回完整时间线（每段在成片里的起止）、字幕列表、配音位置、
    实际生效的设置（含默认值）和提醒。不渲染、不花钱，几秒出结果。"""
    return editor.render(json.loads(json.dumps(spec)), dry_run=True)


@mcp.tool()
def tts(segments: list[str], model: str | None = None, voice: str | None = None,
        instructions: str | None = None, speed: float | None = None,
        gap: float = 0.3, verify: bool = True) -> dict:
    """AI 配音（OpenRouter 语音接口）。segments 是逐句旁白（建议一句一个镜头），
    每句单独生成并去掉首尾静音，wait_job 完成后返回 tts_id、每句时长和试听链接 preview_url。
    - model：默认用服务器 .env 的 OPENROUTER_TTS_MODEL；可用 tts_voices 查模型
    - voice：音色 ID（随模型不同，例如 OpenAI 的 alloy、nova）
    - instructions：语气说明，如「沉稳的知识类讲解，语速稍快」（OpenAI / Gemini / Fish Audio 支持）
    - speed：语速倍率（部分模型支持）；gap：顺排时句与句的间隔秒数
    数字、百分号建议写成汉字读法（如「百分之二」），字幕里再用 corrections 改回「2%」。
    verify=True（默认）：生成后用 Whisper 逐句听写并和原文比对，结果里 verify.flagged 是可能念错的句子。"""
    if not isinstance(segments, list) or not segments or not all(isinstance(x, str) for x in segments):
        raise ValueError("segments 需要是非空的句子列表（每项是文字）")
    return {"job_id": _submit("tts", tts_mod.synthesize, segments, model, voice, instructions,
                              speed, gap, True, None, verify, heavy=False)}


@mcp.tool()
def tts_voices(filter_text: str | None = None) -> list[dict]:
    """列出 OpenRouter 上的语音模型（含价格、可用音色 supported_voices）。filter_text 可按名称过滤，如 seed、fish。"""
    return tts_mod.list_voices(filter_text)


@mcp.tool()
def get_tts(tts_id: str) -> dict:
    """查看一次配音的每句文字、时长和试听链接。"""
    return _tts_view(tts_mod.load(tts_id))


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
def record_web(url: str, steps: list[dict] | None = None, name: str | None = None,
               layout: str = "mobile", settle: float = 0.8, cursor: bool = True) -> dict:
    """网站录屏：用服务器上的浏览器打开网页，按 steps 逐步点击、滚动、输入，录成 1080×1920 竖屏视频
    并导入视频库（无声），返回 job_id；wait_job 完成后给出 video_id 和 marks（每一步在视频里的秒数）。
    - layout："mobile"（默认，手机布局，视口 540×960 CSS 像素、2 倍清晰度，录出 1080×1920）、
      "split"（分屏模板手机屏，视口 540×688，录出 1080×1376）或 "desktop"（电脑布局，1080 像素宽）
    - settle：每步之后停留秒数；cursor：是否显示红色小手指和点击涟漪
    - steps 每一步一个对象，按顺序执行：
        {"click": "免费工具"}  按页面文字点（优先找链接/按钮），或 Playwright 选择器（#id、.class、text=、css=）
        {"click": {"role": "button", "name": "计算"}} / {"placeholder": "..."} / {"label": "..."} 也可以
        {"tap": [x, y]}  按视口坐标点（CSS 像素）
        {"type": "ceramic mug", "into": "input[name=title]", "delay": 60}  逐字输入；{"fill": ..., "into": ...} 直接填
        {"press": "Enter"}；{"scroll": 700, "duration": 1.2}（像素，负数向上）；{"hover": 选择器}
        {"highlight": 选择器, "duration": 1.5}  黄框圈出重点；{"wait": 1.5}；{"wait_for": 选择器}
        {"goto": "https://..."}；{"cursor": false}
      找不到目标时会报错并列出页面上可点的文字，照着改脚本再录。
    用法：先用较少的步骤录一遍，get_frames 看几帧确认页面和位置，再录正式版；
    成片里用 overlays（layer: "base", video_id, start, from, duration）盖在口播画面上，
    口播声音和字幕不受影响；或在 clips 里当独立片段（这段没有声音）。"""
    return {"job_id": _submit("record", webrec.record, url, steps, name, layout, settle, cursor,
                              heavy=False)}


@mcp.tool()
def video_models(filter_text: str | None = None) -> list[dict]:
    """列出 OpenRouter 上的视频生成模型，以及各自支持的时长、分辨率、画幅和价格。"""
    return videogen.list_models(filter_text)


@mcp.tool()
def mux(spec: dict) -> dict:
    """只混音、不动画面：视频画面原样复制（不重新编码、不加任何特效/字幕；speed≠1 时除外），
    只把 AI 配音和背景音乐合进去。用于画面已经做好的成片（例如 Claude 用代码渲染的动画）。
    返回 job_id；wait_job 完成后给出 download_url。
    spec 字段：
    - video_id（必填）：先用 import_video 导入做好的成片
    - voiceover: {tts_id, at?: [每句开始秒数], volume?=1.0}
    - bgm: {name 或 url, volume?=0.12, fade_in?=0.5, fade_out?=1.5, start?=0}，有配音时自动避让
    - original_volume?=0：成片原有声音保留多少；loudnorm?=true
    - speed?=1：整体变速（0.5~2，如 1.4 = 1.4 倍速）。画面和配音一起加速、音调不变，
      BGM 保持原速铺满变速后的时长；voiceover.at 仍按变速前的时间轴写。不为 1 时画面会重新编码。"""
    import specs
    spec = json.loads(json.dumps(spec))
    specs.validate(spec, "mux")
    editor.video_dir(spec["video_id"])
    return {"job_id": _submit("render", editor.mux, spec)}


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


# ---------------------------------------------------------------- 维护：自更新、改配置
APP_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = APP_DIR / ".env"
CONFIG_KEYS = {  # 允许远程设置的配置项；密钥只写不读
    "OPENROUTER_API_KEY": True, "HEYGEN_API_KEY": True,
    "OPENROUTER_TTS_MODEL": False, "OPENROUTER_TTS_VOICE": False, "OPENROUTER_VIDEO_MODEL": False,
    "WHISPER_MODEL": False, "RENDER_WORKERS": False,
}
REPO = os.environ.get("UPDATE_REPO", "Tony11081/douyin-editor")


def _restart_later(cmd: str, unit: str) -> None:
    """用 systemd-run 在服务之外执行，避免重启服务时把自己杀掉。"""
    import subprocess
    if subprocess.run(["which", "systemd-run"], capture_output=True).returncode != 0:
        raise ValueError("服务器没有 systemd-run，无法远程更新，请在终端手动执行")
    subprocess.run(["systemd-run", f"--unit={unit}-{int(time.time())}", "--collect", "--quiet",
                    "/bin/bash", "-lc", cmd], check=True, timeout=30)


@mcp.tool()
def server_info() -> dict:
    """查看服务器上剪辑工具的版本、已配置了哪些密钥（只显示有没有，不显示内容）和默认模型。"""
    ver = (Path(__file__).resolve().parent / "VERSION")
    return {"version": ver.read_text().strip() if ver.exists() else "unknown",
            "keys": {k: bool(os.environ.get(k, "").strip()) for k, secret in CONFIG_KEYS.items() if secret},
            "settings": {k: os.environ.get(k, "") for k, secret in CONFIG_KEYS.items() if not secret}}


@mcp.tool()
def set_config(name: str, value: str) -> dict:
    """修改服务器配置（写入 .env）并自动重启服务，约 5 秒后生效。只允许这些项：
    OPENROUTER_API_KEY、HEYGEN_API_KEY、OPENROUTER_TTS_MODEL、OPENROUTER_TTS_VOICE、
    OPENROUTER_VIDEO_MODEL、WHISPER_MODEL、RENDER_WORKERS。密钥写入后不会被读出。"""
    if name not in CONFIG_KEYS:
        raise ValueError(f"不允许修改 {name}，可改：{', '.join(CONFIG_KEYS)}")
    value = (value or "").strip()
    if not re.fullmatch(r"[\w\-./:+=@]{0,300}", value):
        raise ValueError("值里有不允许的字符（不能有空格、引号、换行）")
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{name}=")] + [f"{name}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)
    _restart_later("sleep 2; systemctl restart douyin-editor", "douyin-editor-restart")
    return {"ok": True, "name": name, "set": bool(value),
            "note": "服务约 5 秒后重启，之后用 server_info 确认"}


@mcp.tool()
def update_server() -> dict:
    """从 GitHub 拉取最新代码并重新安装、重启（配置和密钥保留）。在后台执行，通常 1~5 分钟；
    期间连接会短暂中断，完成后用 server_info 看 version 是否变成最新提交。"""
    cmd = (f"curl -fsSL https://raw.githubusercontent.com/{REPO}/main/setup.sh | bash "
           f"> /var/log/douyin-editor-update.log 2>&1")
    _restart_later(cmd, "douyin-editor-update")
    return {"started": True, "log": "/var/log/douyin-editor-update.log"}


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
        path = tts_mod.preview(m.group(1))
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
