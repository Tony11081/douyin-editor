"""口播视频剪辑核心：下载、转写、按剪辑方案渲染抖音竖屏成片。"""
from __future__ import annotations

import html
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
VIDEOS = DATA_DIR / "videos"
OUTPUTS = DATA_DIR / "outputs"
MUSIC = DATA_DIR / "music"
for _d in (VIDEOS, OUTPUTS, MUSIC):
    _d.mkdir(parents=True, exist_ok=True)

FONT_NAME = os.environ.get("CAPTION_FONT", "Noto Sans CJK SC Black")
FONTS_DIR = os.environ.get("FONTS_DIR", "/usr/share/fonts")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
PUNCT = "，。！？、；：,.!?;:…“”\"'‘’（）()《》【】—-~～ \u3000"
BREAK_PUNCT = set("，。！？、；：,.!?;:…")


class EditorError(Exception):
    pass


# ---------------------------------------------------------------- 工具函数
def run(cmd: list[str], timeout: int = 3600) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise EditorError(f"命令失败: {' '.join(cmd[:6])}...\n{p.stderr[-2500:]}")
    return p.stdout


def probe(path: Path) -> dict[str, Any]:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise EditorError("文件里没有视频轨")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if "rotate" in v.get("tags", {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {
        "duration": float(info["format"].get("duration", v.get("duration", 0))),
        "width": w, "height": h,
        "fps": v.get("avg_frame_rate", "30/1"),
        "codec": v.get("codec_name"),
        "color_transfer": v.get("color_transfer"),
        "color_primaries": v.get("color_primaries"),
        "has_audio": a is not None,
    }


def video_dir(video_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9]{8,32}", video_id):
        raise EditorError("video_id 格式不对")
    d = VIDEOS / video_id
    if not d.exists():
        raise EditorError(f"找不到视频 {video_id}")
    return d


def load_meta(video_id: str) -> dict[str, Any]:
    return json.loads((video_dir(video_id) / "meta.json").read_text())


def fmt_t(t: float) -> str:
    return f"{t:.2f}"


# ---------------------------------------------------------------- 下载
def drive_file_id(url: str) -> str | None:
    for pat in (r"/file/d/([\w-]{10,})", r"[?&]id=([\w-]{10,})", r"/uc\?.*id=([\w-]{10,})"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def drive_folder_id(url: str) -> str | None:
    m = re.search(r"/folders/([\w-]{10,})", url)
    return m.group(1) if m else None


def list_drive_folder(url: str) -> list[dict[str, str]]:
    """列出公开（知道链接的任何人）Drive 文件夹里的文件。"""
    fid = drive_folder_id(url)
    if not fid:
        raise EditorError("不是 Drive 文件夹链接")
    r = requests.get(f"https://drive.google.com/embeddedfolderview?id={fid}#list",
                     headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    items = re.findall(
        r'href="https://drive\.google\.com/file/d/([\w-]+)/view[^"]*".*?'
        r'class="flip-entry-title">([^<]+)<', r.text, re.S)
    if not items:
        raise EditorError("文件夹是空的，或者没有设成「知道链接的任何人可查看」")
    return [{"file_id": i, "name": html.unescape(n).strip(),
             "url": f"https://drive.google.com/file/d/{i}/view"} for i, n in items]


def _stream_to(resp: requests.Response, dest: Path) -> None:
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(1 << 20):
            f.write(chunk)


def download(url: str, dest_dir: Path) -> Path:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    fid = drive_file_id(url) if "drive.google.com" in url or "usercontent" in url else None
    if fid:
        dl = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
        r = s.get(dl, stream=True, timeout=120)
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            page = r.text
            form = re.search(r'<form[^>]+action="([^"]+)"', page)
            fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', page))
            if not form:
                raise EditorError("Drive 不让下载：请把文件设成「知道链接的任何人可查看」")
            r = s.get(html.unescape(form.group(1)), params=fields, stream=True, timeout=120)
            if "text/html" in r.headers.get("Content-Type", ""):
                raise EditorError("Drive 返回的是网页而不是视频，请检查共享权限")
    else:
        r = s.get(url, stream=True, timeout=120)
    r.raise_for_status()
    name = "source"
    cd = r.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    ext = Path(m.group(1)).suffix.lower() if m else Path(url.split("?")[0]).suffix.lower()
    if ext not in {".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".aac"}:
        ext = ".mp4"
    dest = dest_dir / f"{name}{ext}"
    _stream_to(r, dest)
    if dest.stat().st_size < 10_000:
        raise EditorError("下载到的文件太小，可能不是视频")
    return dest


def import_video(url: str, name: str | None = None) -> dict[str, Any]:
    vid = uuid.uuid4().hex[:12]
    d = VIDEOS / vid
    d.mkdir(parents=True)
    try:
        src = download(url, d)
        info = probe(src)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    meta = {"video_id": vid, "name": name or src.name, "url": url, "source": src.name, **info}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta


def import_music(url: str, name: str) -> str:
    name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name)[:40] or "bgm"
    tmp = MUSIC / f".tmp_{uuid.uuid4().hex[:6]}"
    tmp.mkdir()
    try:
        f = download(url, tmp)
        dest = MUSIC / f"{name}{f.suffix}"
        shutil.move(f, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest.name


# ---------------------------------------------------------------- 转写
_model = None
_cc = None


def _to_simplified(text: str) -> str:
    global _cc
    if _cc is None:
        try:
            import opencc  # type: ignore
            _cc = opencc.OpenCC("t2s")
        except Exception:
            _cc = False
    return _cc.convert(text) if _cc else text


def transcribe(video_id: str, language: str = "zh") -> dict[str, Any]:
    global _model
    d = video_dir(video_id)
    meta = load_meta(video_id)
    wav = d / "audio16k.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(d / meta["source"]), "-vn", "-ac", "1",
         "-ar", "16000", str(wav)])
    from faster_whisper import WhisperModel  # 延迟导入，启动快
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
    prompt = "以下是普通话口播，使用简体中文和标点。" if language.startswith("zh") else None
    segs, _ = _model.transcribe(str(wav), language=language, word_timestamps=True,
                                vad_filter=True, initial_prompt=prompt, beam_size=5)
    words, segments = [], []
    for sg in segs:
        first = len(words)
        for w in sg.words or []:
            t = _to_simplified(w.word.strip())
            if t:
                words.append({"i": len(words), "s": round(w.start, 2), "e": round(w.end, 2), "w": t})
        segments.append({"s": round(sg.start, 2), "e": round(sg.end, 2),
                         "text": _to_simplified(sg.text.strip()), "w0": first, "w1": len(words) - 1})
    data = {"language": language, "segments": segments, "words": words}
    (d / "transcript.json").write_text(json.dumps(data, ensure_ascii=False))
    wav.unlink(missing_ok=True)
    return data


def transcript_text(data: dict[str, Any]) -> str:
    """紧凑格式：每句一行 + 逐字时间，方便精确下刀。"""
    lines = []
    W = data["words"]
    for k, sg in enumerate(data["segments"]):
        lines.append(f"S{k} [{fmt_t(sg['s'])}-{fmt_t(sg['e'])}] {sg['text']}")
        ws = W[sg["w0"]: sg["w1"] + 1]
        if ws:
            lines.append("   " + " ".join(f"{fmt_t(w['s'])}~{fmt_t(w['e'])}{w['w']}" for w in ws))
    return "\n".join(lines)


def load_transcript(video_id: str) -> dict[str, Any] | None:
    p = video_dir(video_id) / "transcript.json"
    return json.loads(p.read_text()) if p.exists() else None


# ---------------------------------------------------------------- 字幕
@dataclass
class Cue:
    start: float  # 成片时间
    end: float
    text: str


def _clean(t: str) -> str:
    return "".join(ch for ch in t if ch not in PUNCT or ch == " ").strip()


def _visual_len(t: str) -> float:
    return sum(0.55 if ch.isascii() else 1.0 for ch in t)


def split_text(text: str, max_chars: int) -> list[str]:
    """按标点和长度把一句话切成短字幕（不切断英文单词/数字）。"""
    tokens = re.findall(r"[A-Za-z0-9.%+#@&'-]+|.", text)
    chunks, cur = [], ""
    for tok in tokens:
        if tok in BREAK_PUNCT or tok in "\n":
            if _clean(cur):
                chunks.append(cur)
            cur = ""
            continue
        if _visual_len(_clean(cur + tok)) > max_chars and _clean(cur):
            chunks.append(cur)
            cur = ""
        cur += tok
    if _clean(cur):
        chunks.append(cur)
    out = []
    for c in chunks:
        c = _clean(c)
        # 太短的尾巴并到前一条
        if out and _visual_len(c) <= 2 and _visual_len(out[-1]) + _visual_len(c) <= max_chars + 2:
            out[-1] += c
        else:
            out.append(c)
    return out


def _speech_span(words: list[dict], s: float, e: float) -> tuple[float, float]:
    inside = [w for w in words if w["s"] >= s - 0.05 and w["e"] <= e + 0.05]
    if not inside:
        return s, e
    return max(s, inside[0]["s"]), min(e, inside[-1]["e"])


def _tokens_from_words(words: list[dict], s: float, e: float,
                       corrections: dict[str, str]) -> list[dict]:
    """取片段内的字，套用错字更正（更正项会合并成一个带时间的 token）。"""
    ws = [dict(w) for w in words if s - 0.05 <= (w["s"] + w["e"]) / 2 <= e + 0.05]
    if not ws or not corrections:
        return ws
    joined = "".join(w["w"] for w in ws)
    owner = []
    for idx, w in enumerate(ws):
        owner += [idx] * len(w["w"])
    repl: list[tuple[int, int, str]] = []
    for bad, good in sorted(corrections.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(re.escape(bad), joined):
            a, b = m.start(), m.end()
            if any(not (b <= x or a >= y) for x, y, _ in repl):
                continue
            repl.append((a, b, good))
    if not repl:
        return ws
    out, used = [], set()
    starts = {owner[a]: (a, b, g) for a, b, g in repl}
    i = 0
    while i < len(ws):
        if i in starts:
            a, b, g = starts[i]
            last = owner[b - 1]
            out.append({"s": ws[i]["s"], "e": ws[last]["e"], "w": g})
            used.update(range(i, last + 1))
            i = last + 1
        else:
            out.append(ws[i])
            i += 1
    return out


def build_cues(clips: list[dict], words: list[dict] | None, max_chars: int,
               corrections: dict[str, str]) -> list[Cue]:
    cues: list[Cue] = []
    offset = 0.0
    for c in clips:
        s, e = c["start"], c["end"]
        dur = e - s
        text = c.get("text")
        if text is not None:
            for bad, good in corrections.items():
                text = text.replace(bad, good)
            chunks = split_text(text, max_chars)
            if chunks:
                ss, se = _speech_span(words or [], s, e)
                total = sum(_visual_len(x) for x in chunks)
                t = ss
                for ch in chunks:
                    d = (se - ss) * _visual_len(ch) / total
                    cues.append(Cue(offset + t - s, offset + t + d - s, ch))
                    t += d
        elif words:
            toks = _tokens_from_words(words, s, e, corrections)
            cur, c0, c1 = "", None, None
            for tk in toks:
                piece = tk["w"]
                brk = piece[-1] in BREAK_PUNCT
                body = _clean(piece)
                if body and cur and _visual_len(cur + body) > max_chars:
                    cues.append(Cue(c0, c1, cur))
                    cur, c0 = "", None
                if body:
                    if c0 is None:
                        c0 = max(tk["s"], s) - s + offset
                    cur += body if not (cur and cur[-1].isascii() and body[0].isascii()) else " " + body
                    c1 = min(tk["e"], e) - s + offset
                if brk and cur:
                    cues.append(Cue(c0, c1, cur))
                    cur, c0 = "", None
            if cur:
                cues.append(Cue(c0, c1, cur))
        offset += dur
    # 连续字幕之间不留闪烁空隙，最短 0.35 秒
    cues.sort(key=lambda q: q.start)
    for i, q in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else offset
        if nxt - q.end < 0.4:
            q.end = nxt
        q.end = max(q.end, min(q.start + 0.35, nxt if nxt > q.start else q.start + 0.35))
    return [q for q in cues if q.end > q.start and q.text]


def _ass_color(hex_rgb: str, alpha: str = "00") -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    hh = int(t // 3600)
    mm = int(t % 3600 // 60)
    ss = t % 60
    return f"{hh}:{mm:02d}:{ss:05.2f}"


def _esc(t: str) -> str:
    return t.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def write_ass(path: Path, cues: list[Cue], W: int, H: int, style: dict,
              highlights: list[str], title: dict | None) -> None:
    fs = int(style.get("font_size", round(W * 0.088)))
    y = float(style.get("y", 0.68))
    margin_v = int(H * (1 - y))
    primary = _ass_color(style.get("color", "#FFFFFF"))
    outline_c = _ass_color(style.get("outline_color", "#000000"))
    hi = _ass_color(style.get("highlight_color", "#FFD400"))
    outline = style.get("outline", max(4, fs // 13))
    font = style.get("font", FONT_NAME)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{fs},{primary},{primary},{outline_c},&H80000000,-1,0,0,0,100,100,2,0,"
        f"1,{outline},3,2,40,40,{margin_v},1",
    ]
    if title:
        tfs = int(title.get("font_size", round(W * 0.085)))
        tc = _ass_color(title.get("color", "#FFFFFF"))
        tb = _ass_color(title.get("box_color", "#E6312E"), "10")
        lines.append(
            f"Style: Title,{font},{tfs},{tc},{tc},{tb},{tb},-1,0,0,0,100,100,3,0,"
            f"3,{max(10, tfs // 4)},0,8,60,60,{int(H * float(title.get('y', 0.12)))},1")
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    his = sorted({h for h in highlights if h}, key=len, reverse=True)
    for q in cues:
        txt = _esc(q.text)
        for hword in his:
            hw = _esc(hword)
            if hw in txt:
                txt = txt.replace(hw, f"{{\\c{hi}}}{hw}{{\\c{primary}}}")
        # 轻微弹出动画
        pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}"
        lines.append(f"Dialogue: 0,{_ass_time(q.start)},{_ass_time(q.end)},Cap,,0,0,0,,{pop}{txt}")
    if title:
        end = title.get("duration") or 36000
        ttxt = _esc(title["text"]).replace("\\N", "\\N").replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(float(end))},Title,,0,0,0,,{ttxt}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 渲染
def _color_filter(meta: dict) -> str:
    trc = meta.get("color_transfer") or ""
    prim = meta.get("color_primaries") or ""
    if trc == "smpte2084":  # PQ HDR → SDR 色调映射
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,")
    if prim == "bt2020" or trc == "arib-std-b67":  # iPhone HLG：HLG 本身兼容 SDR，只转色彩矩阵
        return "scale=in_color_matrix=bt2020:out_color_matrix=bt709,"
    return ""


def render(spec: dict[str, Any], progress=lambda msg: None) -> dict[str, Any]:
    video_id = spec["video_id"]
    d = video_dir(video_id)
    meta = load_meta(video_id)
    src = d / meta["source"]
    W, H = int(spec.get("width", 1080)), int(spec.get("height", 1920))
    fps = int(spec.get("fps", 30))
    clips = spec.get("clips") or [{"start": 0, "end": meta["duration"]}]
    for c in clips:
        c["start"] = max(0.0, float(c["start"]))
        c["end"] = min(float(c["end"]), meta["duration"])
        if c["end"] - c["start"] < 0.1:
            raise EditorError(f"片段太短或时间不对: {c}")
    out_id = uuid.uuid4().hex[:12]
    work = OUTPUTS / f".work_{out_id}"
    work.mkdir()
    color = _color_filter(meta)
    focus_y = float(spec.get("focus_y", 0.35))
    try:
        parts = []
        for i, c in enumerate(clips):
            progress(f"剪辑片段 {i + 1}/{len(clips)}")
            dur = c["end"] - c["start"]
            z = max(1.0, float(c.get("zoom", 1.0)))
            zw, zh = math.ceil(W * z / 2) * 2, math.ceil(H * z / 2) * 2
            fy = float(c.get("focus_y", focus_y))
            vf = (f"{color}scale={zw}:{zh}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*{fy},fps={fps},setsar=1,format=yuv420p")
            fade = min(0.015, dur / 4)
            af = (f"aresample=48000,aformat=channel_layouts=stereo,"
                  f"afade=t=in:d={fade},afade=t=out:st={dur - fade:.3f}:d={fade}")
            part = work / f"p{i:03d}.mkv"
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{c['start']:.3f}", "-i", str(src),
                   "-t", f"{dur:.3f}"]
            if not meta["has_audio"]:
                cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            cmd += ["-vf", vf, "-af", af, "-map", "0:v:0", "-map", "0:a:0" if meta["has_audio"] else "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                    "-c:a", "pcm_s16le", str(part)]
            run(cmd)
            parts.append(part)
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        joined = work / "joined.mkv"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", str(joined)])
        total = sum(c["end"] - c["start"] for c in clips)

        # 字幕
        progress("生成字幕")
        cap = spec.get("captions", "auto")
        cues: list[Cue] = []
        style = spec.get("caption_style", {}) or {}
        if cap != "none":
            tr = load_transcript(video_id)
            words = tr["words"] if tr else None
            if not words and not any("text" in c for c in clips):
                raise EditorError("还没有转写，也没给片段文字：先调用 transcribe，或在 clips 里写 text")
            cues = build_cues(clips, words, int(style.get("max_chars", 12)),
                              spec.get("corrections", {}) or {})
        title = spec.get("title")
        ass = work / "subs.ass"
        write_ass(ass, cues, W, H, style, spec.get("highlight_words", []) or [], title)

        # 合成：字幕 + 人声处理 + BGM
        progress("合成成片")
        a = spec.get("audio", {}) or {}
        voice_chain = ["highpass=f=70"]
        if a.get("denoise", True):
            voice_chain.append("afftdn=nf=-25")
        if a.get("loudnorm", True):
            voice_chain.append("loudnorm=I=-14:TP=-1.5:LRA=11")
        voice_chain.append("aresample=48000")
        inputs = ["-i", str(joined)]
        fc = [f"[0:v]subtitles=filename={ass.name}:fontsdir={FONTS_DIR}[v]",
              f"[0:a]{','.join(voice_chain)}[voice]"]
        bgm = spec.get("bgm")
        if bgm:
            bpath = MUSIC / Path(bgm["name"]).name if bgm.get("name") else None
            if bgm.get("url"):
                bpath = MUSIC / import_music(bgm["url"], bgm.get("save_as", f"bgm_{out_id}"))
            if not bpath or not bpath.exists():
                raise EditorError(f"找不到背景音乐 {bgm}")
            vol = float(bgm.get("volume", 0.12))
            fo = float(bgm.get("fade_out", 1.5))
            fi = float(bgm.get("fade_in", 0.5))
            inputs += ["-stream_loop", "-1", "-i", str(bpath)]
            fc += [f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol},"
                   f"atrim=0:{total:.3f},afade=t=in:d={fi},"
                   f"afade=t=out:st={max(0, total - fo):.3f}:d={fo}[bgm]",
                   "[voice]asplit=2[v1][v2]",
                   "[bgm][v2]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=350[bd]",
                   "[v1][bd]amix=inputs=2:duration=first:normalize=0[a]"]
        else:
            fc[-1] = fc[-1].replace("[voice]", "[a]")
        out = OUTPUTS / f"{out_id}.mp4"
        _final(work, inputs, fc, total, fps, spec, out)
        result = {"output_id": out_id, "file": out.name, "duration": round(total, 2),
                  "width": W, "height": H, "captions": [
                      {"start": round(q.start, 2), "end": round(q.end, 2), "text": q.text} for q in cues]}
        (OUTPUTS / f"{out_id}.json").write_text(json.dumps({"spec": spec, **result}, ensure_ascii=False))
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _final(work: Path, inputs: list[str], fc: list[str], total: float, fps: int,
           spec: dict, out: Path) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
           "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", spec.get("preset", "medium"), "-crf", "19",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps),
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    # subtitles 滤镜按相对路径找 .ass，所以在工作目录里执行
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, cwd=work)
    if p.returncode != 0:
        raise EditorError(f"合成失败:\n{p.stderr[-2500:]}")


def frames(kind: str, ident: str, times: list[float], width: int = 360) -> list[bytes]:
    if kind == "output":
        if not re.fullmatch(r"[a-z0-9]{12}", ident):
            raise EditorError("output_id 格式不对")
        path = OUTPUTS / f"{ident}.mp4"
    else:
        path = video_dir(ident) / load_meta(ident)["source"]
    if not path.exists():
        raise EditorError("找不到文件")
    imgs = []
    for t in times[:8]:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(path),
                            "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4",
                            "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                           capture_output=True, timeout=120)
        if p.returncode == 0 and p.stdout:
            imgs.append(p.stdout)
    return imgs
