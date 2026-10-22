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

def _pick_font(wanted: str) -> str:
    """确认字体族真实存在；"xxx Bold" 这种不是字体族名，退回到基础族名（样式里自带加粗）。"""
    try:
        fams = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True,
                              timeout=20).stdout
    except Exception:
        return wanted
    names = {n.strip() for line in fams.splitlines() for n in line.split(",")}
    for cand in (wanted, re.sub(r"\s+(Bold|Black|Heavy|Medium)$", "", wanted),
                 "Noto Sans CJK SC Black", "Noto Sans CJK SC", "WenQuanYi Zen Hei"):
        if cand in names:
            return cand
    return wanted


FONT_NAME = _pick_font(os.environ.get("CAPTION_FONT", "Noto Sans CJK SC Black"))
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


def find_audio_links(page_url: str, keyword: str | None = None) -> list[dict[str, str]]:
    """抓取一个网页（如 Mixkit / Pixabay 曲库页），找出里面的 mp3/m4a 链接。"""
    r = requests.get(page_url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=60)
    r.raise_for_status()
    page = html.unescape(r.text).replace("\\/", "/")
    urls = []
    for m in re.finditer(r"https?://[^\s\"'<>()]+?\.(?:mp3|m4a)(?:\?[^\s\"'<>()]*)?", page):
        u = m.group(0)
        if u not in urls:
            urls.append(u)
    out = []
    for u in urls:
        name = Path(u.split("?")[0]).stem
        if keyword and keyword.lower() not in (name + u).lower():
            continue
        out.append({"name": name, "url": u})
    return out[:60]


RVM_URL = ("https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/"
           "rvm_mobilenetv3_fp32.onnx")


def make_matte(video: Path, out: Path, W: int, H: int, fps: int, progress=lambda m: None) -> None:
    """人像抠像：RobustVideoMatting（ONNX，CPU）逐帧算人物透明度，输出灰度遮罩视频。
    半分辨率推理再放大，速度约为全分辨率的 4 倍；递归状态让边缘在帧间稳定。"""
    import numpy as np
    import onnxruntime as ort
    model = _cached_download(RVM_URL, "models")
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, (os.cpu_count() or 2))
    sess = ort.InferenceSession(str(model), so, providers=["CPUExecutionProvider"])
    w, h = W // 2, H // 2
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
                            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                            "-vf", f"scale={W}:{H}:flags=bicubic", "-c:v", "ffv1", "-pix_fmt", "gray",
                            str(out)], stdin=subprocess.PIPE)
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    ratio = np.array([0.5], np.float32)     # 半分辨率输入上再缩一半做粗推理
    n = 0
    try:
        while True:
            buf = dec.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            src = np.frombuffer(buf, np.uint8).reshape(h, w, 3).transpose(2, 0, 1)[None].astype(np.float32) / 255
            fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2],
                                             "r4i": rec[3], "downsample_ratio": ratio})
            enc.stdin.write((np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8).tobytes())
            n += 1
            if n % 60 == 0:
                progress(f"抠像 {n} 帧")
    finally:
        enc.stdin.close()
        enc.wait()
        dec.wait()
    if enc.returncode != 0 or n == 0:
        raise EditorError("抠像失败")


def _cached_download(url: str, kind: str) -> Path:
    """下载一次并按 URL 缓存（叠加层、音频床等素材）。"""
    import hashlib
    d = DATA_DIR / kind
    d.mkdir(exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    hit = next(iter(d.glob(f"{key}.*")), None)
    if hit:
        return hit
    tmp = d / f".tmp_{key}"
    tmp.mkdir(exist_ok=True)
    try:
        f = download(url, tmp)
        ext = Path(url.split("?")[0]).suffix.lower() or f.suffix
        dest = d / f"{key}{ext}"
        shutil.move(f, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


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
    # 直接用 ffmpeg 解码成 16kHz 单声道 float32 数组交给 Whisper，
    # 不经过 PyAV（新版 PyAV 和 faster-whisper 的 decode_audio 不兼容）
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(d / meta["source"]), "-vn",
                        "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                       capture_output=True, timeout=1800)
    if p.returncode != 0:
        raise EditorError(f"提取音频失败:\n{p.stderr.decode(errors='ignore')[-1500:]}")
    audio = np.frombuffer(p.stdout, dtype=np.float32)
    if audio.size < 16000:
        raise EditorError("音频太短或没有声音")
    from faster_whisper import WhisperModel  # 延迟导入，启动快
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
    prompt = "以下是普通话口播，使用简体中文和标点。" if language.startswith("zh") else None
    segs, _ = _model.transcribe(audio, language=language, word_timestamps=True,
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
    return data


def whisper_file(path: Path, language: str = "zh") -> str:
    """把一段音频转成文字（用于核对配音念得对不对）。"""
    global _model
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True, timeout=600)
    if p.returncode != 0:
        raise EditorError(f"提取音频失败:\n{p.stderr.decode(errors='ignore')[-800:]}")
    audio = np.frombuffer(p.stdout, dtype=np.float32)
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
    prompt = "以下是普通话，使用简体中文和标点。" if language.startswith("zh") else None
    segs, _ = _model.transcribe(audio, language=language, initial_prompt=prompt, beam_size=5,
                                vad_filter=False)
    return _to_simplified("".join(sg.text for sg in segs).strip())


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


def _balanced(tokens: list[str], max_chars: int) -> list[str]:
    """把过长的一段切成长度尽量相等的几行，只在 token 边界切（不切断英文/数字）。"""
    total = sum(_visual_len(t) for t in tokens)
    k = max(1, math.ceil(total / max_chars))
    target = total / k
    parts, cur, acc = [], "", 0.0
    for tok in tokens:
        L = _visual_len(tok)
        if cur and len(parts) < k - 1 and acc + L / 2 > target * (len(parts) + 1):
            parts.append(cur)
            cur = ""
        cur += tok
        acc += L
    if cur:
        parts.append(cur)
    return parts


_jieba = None


def _words(text: str) -> list[str]:
    """分词：有 jieba 就按中文词切，否则按字；英文/数字整体保留。"""
    global _jieba
    if _jieba is None:
        try:
            import jieba  # type: ignore
            jieba.setLogLevel(60)
            _jieba = jieba
        except Exception:
            _jieba = False
    out: list[str] = []
    for m in re.finditer(r"[A-Za-z0-9.%+#@&'-]+|\s+|[一-鿿]+|.", text):
        seg = m.group(0)
        if _jieba and re.fullmatch(r"[一-鿿]+", seg):
            out += _jieba.lcut(seg)
        elif re.fullmatch(r"[一-鿿]+", seg):
            out += list(seg)
        else:
            out.append(seg)
    return out


def split_text(text: str, max_chars: int) -> list[str]:
    """按标点、空格切成短字幕；单段太长时按词平均切成几行。不切断词、英文和数字。"""
    tokens = _words(text)
    phrases, cur = [], []
    for tok in tokens:
        if tok in BREAK_PUNCT or tok.isspace():
            if cur:
                phrases.append(cur)
            cur = []
        elif tok not in PUNCT:
            cur.append(tok)
    if cur:
        phrases.append(cur)
    out: list[str] = []
    for ph in phrases:
        s = "".join(ph)
        if _visual_len(s) > max_chars:
            pieces = _balanced(ph, max_chars)
        else:
            pieces = [s]
        for c in pieces:
            # 太短的尾巴并到前一条
            if out and _visual_len(c) <= 2 and _visual_len(out[-1]) + _visual_len(c) <= max_chars + 1:
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
    all_words = words
    for c in clips:
        s, e = c["start"], c["end"]
        dur = e - s
        text = c.get("text")
        words = c.get("_words", all_words)
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
    return _finish_cues(cues, offset)


def _finish_cues(cues: list[Cue], total: float) -> list[Cue]:
    # 连续字幕之间不留闪烁空隙，最短 0.35 秒
    cues.sort(key=lambda q: q.start)
    for i, q in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else total
        if nxt - q.end < 0.4:
            q.end = nxt
        q.end = max(q.end, min(q.start + 0.35, nxt if nxt > q.start else q.start + 0.35))
    return [q for q in cues if q.end > q.start and q.text]


def voiceover_cues(placed: list[dict], max_chars: int, corrections: dict[str, str],
                   total: float) -> list[Cue]:
    """配音字幕：每句文字按长度切成短行，在这句配音的时长里按字数分配时间。"""
    cues: list[Cue] = []
    for p in placed:
        text = p["text"]
        for bad, good in corrections.items():
            text = text.replace(bad, good)
        chunks = split_text(text, max_chars)
        if not chunks:
            continue
        span = p["end"] - p["start"]
        tl = sum(_visual_len(x) for x in chunks) or 1
        t = p["start"]
        for ch in chunks:
            d = span * _visual_len(ch) / tl
            cues.append(Cue(t, t + d, ch))
            t += d
    # 句与句之间的停顿保留字幕（_finish_cues 只填补 0.4 秒内的空隙）
    return _finish_cues(cues, total)


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


CAPTION_PRESETS: dict[str, dict[str, Any]] = {
    # 抖音口播最常见：白字粗黑描边 + 投影，重点词黄色放大
    "douyin": {"color": "#FFFFFF", "outline_color": "#111111", "highlight_color": "#FFE14D",
               "outline_ratio": 0.085, "shadow": 5, "box": False, "size_ratio": 0.097},
    # 黑底白字条（更稳重，适合知识类）
    "box": {"color": "#FFFFFF", "outline_color": "#000000", "highlight_color": "#FFE14D",
            "outline_ratio": 0.0, "shadow": 0, "box": True, "size_ratio": 0.085},
    # 黄字黑边（更吸睛）
    "yellow": {"color": "#FFE14D", "outline_color": "#111111", "highlight_color": "#FFFFFF",
               "outline_ratio": 0.085, "shadow": 5, "box": False, "size_ratio": 0.097},
}


def write_ass(path: Path, cues: list[Cue], W: int, H: int, style: dict,
              highlights: list[str], title: dict | None) -> None:
    pre = CAPTION_PRESETS.get(style.get("preset", "douyin"), CAPTION_PRESETS["douyin"])
    st = {**pre, **style}
    fs = int(st.get("font_size", round(W * st["size_ratio"])))
    y = float(st.get("y", 0.70))
    margin_v = int(H * (1 - y))
    primary = _ass_color(st["color"])
    outline_c = _ass_color(st["outline_color"])
    hi = _ass_color(st["highlight_color"])
    outline = st.get("outline", max(3, round(fs * st["outline_ratio"])))
    shadow = st.get("shadow", 5)
    font = st.get("font", FONT_NAME)
    hi_scale = int(st.get("highlight_scale", 112))
    if st.get("box"):
        cap_style = (f"Style: Cap,{font},{fs},{primary},{primary},&H00000000,&H66000000,-1,0,0,0,"
                     f"100,100,1,0,3,{max(12, fs // 4)},0,2,60,60,{margin_v},1")
    else:
        cap_style = (f"Style: Cap,{font},{fs},{primary},{primary},{outline_c},&H96000000,-1,0,0,0,"
                     f"100,100,1,0,1,{outline},{shadow},2,40,40,{margin_v},1")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        cap_style,
    ]
    if title:
        tfs = int(title.get("font_size", round(W * 0.128)))
        t1 = _ass_color(title.get("color", "#FFE14D"))       # 第一行：黄
        t2 = _ass_color(title.get("color2", "#FFFFFF"))      # 第二行起：白
        tout = _ass_color(title.get("outline_color", "#111111"))
        ty = int(H * float(title.get("y", 0.085)))
        lines.append(
            f"Style: Title,{font},{tfs},{t1},{t1},{tout},&H96000000,-1,0,0,0,100,100,2,0,"
            f"1,{max(4, round(tfs * 0.09))},6,8,50,50,{ty},1")
        lines.append(
            f"Style: Title2,{font},{int(tfs * 0.86)},{t2},{t2},{tout},&H96000000,-1,0,0,0,100,100,2,0,"
            f"1,{max(4, round(tfs * 0.08))},6,8,50,50,{ty + int(tfs * 1.22)},1")
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    # 行内覆盖标签用标准写法 \c&HBBGGRR&（6 位 + 结尾 &），旧版 libass 才认得
    hi_in = "&H" + _ass_color(st["highlight_color"])[4:] + "&"
    pr_in = "&H" + _ass_color(st["color"])[4:] + "&"
    his = sorted({h for h in highlights if h}, key=len, reverse=True)
    for q in cues:
        txt = _esc(q.text)
        # 先标出要高亮的区间，避免短词在已替换的标签里再次匹配
        marks = [False] * len(txt)
        for hword in his:
            hw = _esc(hword)
            start = 0
            while (k := txt.find(hw, start)) >= 0:
                if not any(marks[k:k + len(hw)]):
                    for j in range(k, k + len(hw)):
                        marks[j] = True
                start = k + len(hw)
        pieces, on = [], False
        for ch, m in zip(txt, marks):
            if m and not on:
                pieces.append(f"{{\\c{hi_in}\\fscx{hi_scale}\\fscy{hi_scale}}}")
            elif not m and on:
                pieces.append(f"{{\\c{pr_in}\\fscx100\\fscy100}}")
            pieces.append(ch)
            on = m
        body = "".join(pieces)
        has_hi = any(marks)
        # 弹出动画：从 85% 放大到 100%（有放大的重点词时改成淡入，避免缩放互相覆盖）
        pop = "\\fad(40,0)" if has_hi else "\\fscx85\\fscy85\\t(0,80,\\fscx100\\fscy100)"
        if body.startswith("{"):          # 合并成一个标签块
            body = "{" + pop + body[1:]
        else:
            body = "{" + pop + "}" + body
        lines.append(f"Dialogue: 0,{_ass_time(q.start)},{_ass_time(q.end)},Cap,,0,0,0,,{body}")
    if title:
        end = float(title.get("duration") or 36000)
        rows = [r.strip() for r in title["text"].replace("\\N", "\n").split("\n") if r.strip()]
        if len(rows) > 2:
            rows = [rows[0], " ".join(rows[1:])]
        for k, row in enumerate(rows):
            # 第一行先弹出，第二行稍后弹出
            anim = ("{\\fad(150,0)\\fscx60\\fscy60\\t(0,170,\\fscx108\\fscy108)"
                    "\\t(170,250,\\fscx100\\fscy100)}")
            lines.append(f"Dialogue: 1,{_ass_time(0.0 if k == 0 else 0.2)},{_ass_time(end)},"
                         f"{'Title' if k == 0 else 'Title2'},,0,0,0,,{anim}{_esc(row)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 渲染
_HAS_ZSCALE: bool | None = None


def _has_zscale() -> bool:
    global _HAS_ZSCALE
    if _HAS_ZSCALE is None:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
        _HAS_ZSCALE = " zscale " in p.stdout and " tonemap " in p.stdout
    return _HAS_ZSCALE


def _color_filter(meta: dict, color: dict) -> str:
    """HDR（iPhone HLG / PQ）→ SDR 色调映射 + 简单调色。返回以逗号结尾的滤镜串。"""
    trc = meta.get("color_transfer") or ""
    prim = meta.get("color_primaries") or ""
    mode = color.get("mode", "auto")
    hdr = trc in ("arib-std-b67", "smpte2084")
    chain = ""
    if hdr and mode in ("auto", "tonemap") and _has_zscale():
        npl = float(color.get("npl", 100))
        algo = color.get("tonemap", "mobius")
        param = color.get("param")
        desat = float(color.get("desat", 0))
        tm = f"tonemap=tonemap={algo}:desat={desat}" + (f":param={param}" if param is not None else "")
        chain = (f"zscale=tin={trc}:pin=bt2020:min=bt2020nc:rin=tv:t=linear:npl={npl},"
                 f"format=gbrpf32le,zscale=p=bt709,{tm},"
                 f"zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
    elif (hdr or prim == "bt2020") and mode != "none":
        chain = "scale=in_color_matrix=bt2020:out_color_matrix=bt709,"
    b = float(color.get("brightness", 0.0))
    c = float(color.get("contrast", 1.0))
    s = float(color.get("saturation", 1.0))
    g = float(color.get("gamma", 1.0))
    if (b, c, s, g) != (0.0, 1.0, 1.0, 1.0):
        chain += f"eq=brightness={b}:contrast={c}:saturation={s}:gamma={g},"
    w = float(color.get("warmth", 0.0))
    if w:
        k = 0.08 * w
        chain += f"colorbalance=rm={k:.3f}:bm={-k:.3f}:rs={k / 2:.3f}:bs={-k / 2:.3f},"
    return chain


def _sfx_files() -> dict[str, Path]:
    """合成两个无版权音效：嗖（转场）和 啵（标题弹出）。生成一次后缓存。"""
    sd = DATA_DIR / "sfx"
    sd.mkdir(exist_ok=True)
    files = {"whoosh": sd / "whoosh.wav", "pop": sd / "pop.wav"}
    if not files["whoosh"].exists():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "anoisesrc=d=0.45:c=pink:r=48000:a=0.6", "-af",
             "highpass=f=500,lowpass=f=7000,afade=t=in:d=0.22:curve=exp,"
             "afade=t=out:st=0.22:d=0.23:curve=exp,aformat=channel_layouts=stereo,"
             "aecho=0.6:0.4:40:0.3,volume=0.8", str(files["whoosh"])])
    if not files["pop"].exists():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "sine=f=880:d=0.18:r=48000", "-f", "lavfi", "-i", "sine=f=1760:d=0.18:r=48000",
             "-filter_complex",
             "[0][1]amix=inputs=2:normalize=0,afade=t=in:d=0.005,afade=t=out:st=0.01:d=0.17:curve=exp,"
             "aformat=channel_layouts=stereo,volume=0.6", str(files["pop"])])
    return files


EFFECT_DEFAULTS = {"drift": 0.04, "oversample": 1.5, "flash_first": True, "sfx": True,
                   "sfx_volume": 0.35, "progress_bar": True, "bar_color": "#FFE14D", "bar_height": 10}
TOL = 0.05  # 允许的时间误差（秒），大约一帧多一点


def plan_render(spec: dict[str, Any]) -> dict[str, Any]:
    """校验剪辑方案并算出完整的执行计划（时间线、字幕、配音位置、实际生效的设置）。
    不调用 ffmpeg、不产生费用；有任何做不到或不明确的地方直接报错，不猜。"""
    import specs  # 延迟导入，避免循环引用
    specs.validate(spec, "render")
    video_id = spec["video_id"]
    video_dir(video_id)
    meta = load_meta(video_id)
    warnings: list[str] = []
    W, H = int(spec.get("width", 1080)), int(spec.get("height", 1920))
    fps = int(spec.get("fps", 30))
    if W % 2 or H % 2:
        raise EditorError(f"width/height 必须是偶数（现在 {W}x{H}）")
    clips = spec.get("clips") or [{"start": 0, "end": meta["duration"]}]
    metas: dict[str, dict[str, Any]] = {video_id: meta}

    def clip_meta(c: dict) -> dict[str, Any]:
        vid = c.get("video_id") or video_id
        if vid not in metas:
            video_dir(vid)
            metas[vid] = load_meta(vid)
        return metas[vid]

    timeline, t_out = [], 0.0
    for i, c in enumerate(clips):
        cm = clip_meta(c)
        s0 = float(c.get("start", 0))
        e0 = float(c.get("end", cm["duration"]))
        if e0 > cm["duration"] + TOL:
            raise EditorError(f"clips[{i}].end = {e0} 超过视频 {cm['video_id']} 的时长 "
                              f"{cm['duration']:.2f} 秒")
        c["start"], c["end"] = s0, min(e0, cm["duration"])
        if c["end"] - c["start"] < 0.1:
            raise EditorError(f"clips[{i}] 太短或 start ≥ end（{s0} → {e0}），每段至少 0.1 秒")
        dur = c["end"] - c["start"]
        timeline.append({"index": i, "video_id": cm["video_id"], "src_start": round(c["start"], 3),
                         "src_end": round(c["end"], 3), "out_start": round(t_out, 3),
                         "out_end": round(t_out + dur, 3), "zoom": c.get("zoom", 1.0)})
        t_out += dur
    total = t_out

    eff = {**EFFECT_DEFAULTS, **(spec.get("effects") or {})}
    defaults_used = sorted(set(EFFECT_DEFAULTS) - set(spec.get("effects") or {}))

    vo = spec.get("voiceover")
    vo_placed: list[dict] = []
    if vo:
        import tts
        vo_placed = tts.plan_voice(vo["tts_id"], vo.get("at"), total)

    cap = spec.get("captions", "auto")
    style = spec.get("caption_style") or {}
    max_chars = int(style.get("max_chars", 12))
    corrections = spec.get("corrections") or {}
    cues: list[Cue] = []
    caption_mode = "none"
    if cap == "voiceover" and not vo:
        raise EditorError('captions = "voiceover" 但没有 voiceover')
    if cap != "none":
        tr = load_transcript(video_id)
        words = tr["words"] if tr else None
        has_text = any("text" in c for c in clips)
        if vo and (cap == "voiceover" or (not words and not has_text)):
            cues = voiceover_cues(vo_placed, max_chars, corrections, total)
            caption_mode = "voiceover"
        else:
            if not words and not has_text:
                raise EditorError("还没有转写，也没给片段文字：先调用 transcribe，或在 clips 里写 text，"
                                  '或设 captions: "none"')
            for c in clips:
                vid = c.get("video_id")
                if vid and vid != video_id:
                    t2 = load_transcript(vid)
                    if not t2 and "text" not in c:
                        raise EditorError(f"clips 里来自视频 {vid} 的片段没有转写也没写 text，字幕没法生成")
                    c["_words"] = t2["words"] if t2 else []
            try:
                cues = build_cues(clips, words, max_chars, corrections)
            finally:
                for c in clips:
                    c.pop("_words", None)
            caption_mode = "clip_text+transcript" if has_text and words else (
                "clip_text" if has_text else "transcript")
        cap_text = "".join(q.text for q in cues)
        for h in spec.get("highlight_words") or []:
            if h not in cap_text:
                warnings.append(f"高亮词「{h}」没有出现在字幕里，不会被标出")
        for bad in corrections:
            if bad in cap_text:
                warnings.append(f"更正「{bad}」后字幕里仍有「{bad}」")
    title = spec.get("title")
    if title and title.get("duration") and float(title["duration"]) > total + TOL:
        warnings.append(f"标题时长 {title['duration']} 秒超过成片 {total:.2f} 秒，会显示到结尾")
    bgm = spec.get("bgm")
    if bgm:
        if not bgm.get("name") and not bgm.get("url"):
            raise EditorError("bgm 需要 name（list_music 里的文件名）或 url")
        if bgm.get("name") and not (MUSIC / Path(bgm["name"]).name).exists():
            raise EditorError(f"音乐库里没有 {bgm['name']}（用 list_music 查）")
    for i, ov in enumerate(spec.get("overlays") or []):
        if float(ov.get("start", 0)) >= total:
            raise EditorError(f"overlays[{i}].start = {ov.get('start')} 超出成片时长 {total:.2f}")
    pre = CAPTION_PRESETS.get(style.get("preset", "douyin"), CAPTION_PRESETS["douyin"])
    return {"clips": clips, "metas": metas, "timeline": timeline, "total": round(total, 3),
            "W": W, "H": H, "fps": fps, "eff": eff, "vo_placed": vo_placed, "cues": cues,
            "warnings": warnings,
            "applied": {"width": W, "height": H, "fps": fps, "duration": round(total, 3),
                        "effects": eff, "effects_defaults_used": defaults_used,
                        "caption_mode": caption_mode, "caption_style": {**pre, **style},
                        "audio": {"denoise": True, "loudnorm": True, **(spec.get("audio") or {})},
                        "preset": spec.get("preset", "medium")}}


def plan_view(plan: dict[str, Any]) -> dict[str, Any]:
    return {"duration": plan["total"], "timeline": plan["timeline"],
            "voiceover": [{"start": round(p["start"], 2), "end": round(p["end"], 2), "text": p["text"]}
                          for p in plan["vo_placed"]],
            "captions": [{"start": round(q.start, 2), "end": round(q.end, 2), "text": q.text}
                         for q in plan["cues"]],
            "applied": plan["applied"], "warnings": plan["warnings"]}


def render(spec: dict[str, Any], progress=lambda msg: None, dry_run: bool = False) -> dict[str, Any]:
    plan = plan_render(spec)
    if dry_run:
        return {"dry_run": True, **plan_view(plan)}
    video_id = spec["video_id"]
    clips, metas = plan["clips"], plan["metas"]
    W, H, fps, eff = plan["W"], plan["H"], plan["fps"], plan["eff"]
    total = plan["total"]

    def clip_meta(c: dict) -> dict[str, Any]:
        return metas[c.get("video_id") or video_id]

    out_id = uuid.uuid4().hex[:12]
    work = OUTPUTS / f".work_{out_id}"
    work.mkdir()
    color_spec = spec.get("color", {}) or {}
    focus_y = float(spec.get("focus_y", 0.35))
    whoosh_at: list[float] = []
    try:
        parts = []
        t_out = 0.0
        for i, c in enumerate(clips):
            progress(f"剪辑片段 {i + 1}/{len(clips)}")
            cm = clip_meta(c)
            csrc = VIDEOS / cm["video_id"] / cm["source"]
            color = _color_filter(cm, color_spec)
            dur = c["end"] - c["start"]
            z = float(c.get("zoom", 1.0))
            fy = float(c.get("focus_y", focus_y))
            drift = float(c.get("drift", eff["drift"]))
            if drift > 0:
                # 先放大到 oversample 倍再用 zoompan 缓慢推拉，减轻 zoompan 的像素抖动
                os_ = float(eff["oversample"])
                bw, bh = math.ceil(W * os_ / 2) * 2, math.ceil(H * os_ / 2) * 2
                zw, zh = math.ceil(bw * z / 2) * 2, math.ceil(bh * z / 2) * 2
                n = max(1, round(dur * fps))
                zexpr = (f"1+{drift}*on/{n}" if i % 2 == 0 or z > 1.0
                         else f"1+{drift}-{drift}*on/{n}")
                geo = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase:flags=bicubic,"
                       f"crop={bw}:{bh}:(iw-{bw})/2:(ih-{bh})*{fy},fps={fps},"
                       f"zoompan=z='{zexpr}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*{fy}':"
                       f"d=1:s={W}x{H}:fps={fps}")
            else:
                zw, zh = math.ceil(W * z / 2) * 2, math.ceil(H * z / 2) * 2
                geo = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase:flags=lanczos,"
                       f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*{fy},fps={fps}")
            flash = ""
            if c.get("flash") or (i == 0 and eff["flash_first"]):
                flash = ",fade=t=in:st=0:d=0.15:color=white"
            if eff["sfx"] and i > 0 and (z >= 1.08 or c.get("flash")):
                whoosh_at.append(max(0.0, t_out - 0.12))
            vf = f"{color}{geo}{flash},setsar=1,format=yuv420p"
            t_out += dur
            fade = min(0.015, dur / 4)
            af = (f"aresample=48000,aformat=channel_layouts=stereo,"
                  f"afade=t=in:d={fade},afade=t=out:st={dur - fade:.3f}:d={fade}")
            part = work / f"p{i:03d}.mkv"
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{c['start']:.3f}", "-i", str(csrc),
                   "-t", f"{dur:.3f}"]
            if not cm["has_audio"]:
                cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            cmd += ["-vf", vf, "-af", af, "-map", "0:v:0", "-map", "0:a:0" if cm["has_audio"] else "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                    "-c:a", "pcm_s16le", str(part)]
            run(cmd)
            parts.append(part)
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        joined = work / "joined.mkv"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", str(joined)])
        # AI 配音：每句放到成片时间轴上（位置已在计划里校验过）
        vo = spec.get("voiceover") or None
        vo_track: Path | None = None
        vo_placed: list[dict] = plan["vo_placed"]
        if vo:
            import tts  # 延迟导入，避免循环引用
            progress("铺配音")
            vo_track = work / "voiceover.wav"
            tts.build_voice_track(vo["tts_id"], vo.get("at"), total, vo_track)
        progress("生成字幕")
        cues: list[Cue] = plan["cues"]
        style = spec.get("caption_style", {}) or {}
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
        nin = 1
        overlays = spec.get("overlays", []) or []
        behind = [o for o in overlays if o.get("layer") == "behind"]
        front = [o for o in overlays if o.get("layer") != "behind"]
        fv: list[str] = []
        cur = "[0:v]"

        def _ov_input(ov: dict) -> None:
            nonlocal nin, inputs
            opath = _cached_download(ov["url"], "overlays")
            dec = ["-c:v", "libvpx-vp9"] if opath.suffix.lower() == ".webm" else []
            inputs += [*dec, "-itsoffset", f"{float(ov.get('start', 0)):.3f}", "-i", str(opath)]
            nin += 1

        if behind:
            # 字在人后面：背景 → 背后文字层 → 抠出的人物 → 字幕/前景层
            progress("抠像")
            matte = work / "matte.mkv"
            make_matte(joined, matte, W, H, fps, progress)
            inputs += ["-i", str(matte)]
            mi = nin
            nin += 1
            fv.append(f"{cur}split=2[bg0][fg0]")
            cur = "[bg0]"
            for k, ov in enumerate(behind):
                idx = nin
                _ov_input(ov)
                fv.append(f"[{idx}:v]format=yuva420p[bh{k}]")
                fv.append(f"{cur}[bh{k}]overlay=x={int(ov.get('x', 0))}:y={int(ov.get('y', 0))}:"
                          f"eof_action=pass:format=auto[bb{k}]")
                cur = f"[bb{k}]"
            feather = float((spec.get("matte") or {}).get("feather", 1.5))
            soft = f",gblur=sigma={feather}" if feather > 0 else ""
            fv.append(f"[{mi}:v]format=gray{soft}[mk]")
            fv.append("[fg0][mk]alphamerge[person]")
            fv.append(f"{cur}[person]overlay=0:0:format=auto[comp]")
            cur = "[comp]"
        vlabel = "[vs]"
        fv.append(f"{cur}subtitles=filename={ass.name}:fontsdir={FONTS_DIR}{vlabel}")
        voice_expr = f"[0:a]{','.join(voice_chain)}[voice]"
        if vo_track:
            vi = nin
            inputs += ["-i", str(vo_track)]
            nin += 1
            vo_chain = (f"[{vi}:a]aresample=48000,aformat=channel_layouts=stereo,"
                        f"volume={float(vo.get('volume', 1.0))}")
            if a.get("loudnorm", True):
                vo_chain += ",loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
            ovol = float(vo.get("original_volume", 0.0))
            if ovol > 0 and any(m["has_audio"] for m in metas.values()):
                voice_expr = (f"[0:a]{','.join(voice_chain)},volume={ovol}[orig];{vo_chain}[vo];"
                              f"[orig][vo]amix=inputs=2:duration=first:normalize=0,"
                              f"alimiter=limit=0.95[voice]")
            else:
                voice_expr = f"{vo_chain}[voice]"
        fc = [";".join(fv), voice_expr]
        # 前景透明动画层（例如代码渲染的 VP9 alpha webm），按成片时间叠加
        for k, ov in enumerate(front):
            opath = _cached_download(ov["url"], "overlays")
            off = float(ov.get("start", 0))
            dec = ["-c:v", "libvpx-vp9"] if opath.suffix.lower() == ".webm" else []
            inputs += [*dec, "-itsoffset", f"{off:.3f}", "-i", str(opath)]
            fc.append(f"[{nin}:v]format=yuva420p,setpts=PTS[ov{k}]")
            fc.append(f"{vlabel}[ov{k}]overlay=x={int(ov.get('x', 0))}:y={int(ov.get('y', 0))}:"
                      f"eof_action=pass:format=auto[vo{k}]")
            vlabel = f"[vo{k}]"
            nin += 1
        # 顶部进度条
        if eff["progress_bar"]:
            bc = eff["bar_color"].lstrip("#")
            bh_ = int(eff["bar_height"])
            inputs += ["-f", "lavfi", "-i", f"color=c=0x{bc}:s={W}x{bh_}:r={fps}:d={total + 1:.3f}"]
            fc.append(f"{vlabel}[{nin}:v]overlay=x='-w+W*t/{total:.3f}':y=0:shortest=1[vb]")
            vlabel = "[vb]"
            nin += 1
        fc.append(f"{vlabel}null[v]")
        mix = ["[voice]"]
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
            ss = float(bgm.get("start", 0))
            inputs += ["-stream_loop", "-1", "-ss", f"{ss:.2f}", "-i", str(bpath)]
            fc += [f"[{nin}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol},"
                   f"atrim=0:{total:.3f},afade=t=in:d={fi},"
                   f"afade=t=out:st={max(0, total - fo):.3f}:d={fo}[bgm]",
                   "[voice]asplit=2[v1][v2]",
                   "[bgm][v2]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=350[bd]"]
            mix = ["[v1]", "[bd]"]
            nin += 1
        # 音效：转场"嗖"、标题"啵"
        hits: list[tuple[str, float]] = [("whoosh", t) for t in whoosh_at]
        if eff["sfx"] and title:
            hits.append(("pop", 0.05))
            if "\n" in title["text"].replace("\\N", "\n"):
                hits.append(("pop", 0.25))
        if hits:
            sf = _sfx_files()
            sv = float(eff["sfx_volume"])
            for k, (kind, t) in enumerate(hits):
                inputs += ["-i", str(sf[kind])]
                ms = int(t * 1000)
                fc.append(f"[{nin}:a]volume={sv},adelay={ms}|{ms}[sx{k}]")
                mix.append(f"[sx{k}]")
                nin += 1
        if len(mix) > 1:
            fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[a]")
        else:
            fc[1] = fc[1].replace("[voice]", "[a]")
        out = OUTPUTS / f"{out_id}.mp4"
        _final(work, inputs, fc, total, fps, spec, out)
        progress("成片自检")
        checks = verify_output(out, {"width": W, "height": H, "fps": fps, "duration": total,
                                     "voiceover": vo_placed})
        result = {"output_id": out_id, "file": out.name, "duration": round(total, 2),
                  "width": W, "height": H, "checks": checks, "applied": plan["applied"],
                  "warnings": plan["warnings"], "voiceover": [
                      {"start": round(p["start"], 2), "end": round(p["end"], 2), "text": p["text"]}
                      for p in vo_placed], "captions": [
                      {"start": round(q.start, 2), "end": round(q.end, 2), "text": q.text} for q in cues]}
        (OUTPUTS / f"{out_id}.json").write_text(json.dumps({"spec": spec, **result}, ensure_ascii=False))
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _mean_db(path: Path, ss: float, dur: float) -> float:
    p = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{ss:.3f}", "-t", f"{max(0.05, dur):.3f}", "-i",
                        str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=300)
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", p.stderr)
    return -120.0 if not m or m.group(1) == "-inf" else float(m.group(1))


def _loudness(path: Path) -> float | None:
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=900)
    m = re.findall(r"I:\s*(-?[\d.]+) LUFS", p.stderr)
    return float(m[-1]) if m else None


def _vhash(path: Path) -> str:
    return run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
                "-f", "hash", "-hash", "md5", "-"]).strip()


def verify_output(out: Path, expect: dict[str, Any]) -> dict[str, Any]:
    """成片自检：分辨率、帧率、时长、有没有声音、每句配音位置是否真的有声音、整体响度。"""
    items: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        items.append({"check": name, "ok": bool(ok), "detail": detail})

    info = probe(out)
    if "width" in expect:
        add("分辨率", (info["width"], info["height"]) == (expect["width"], expect["height"]),
            f"{info['width']}x{info['height']}（要求 {expect['width']}x{expect['height']}）")
    if "fps" in expect:
        num_, _, den = str(info["fps"]).partition("/")
        real = float(num_) / float(den or 1) if float(den or 1) else 0
        add("帧率", abs(real - expect["fps"]) < 0.01, f"{real:g}（要求 {expect['fps']}）")
    fps = float(expect.get("fps", 30))
    tol = max(2 / fps, 0.08)
    add("时长", abs(info["duration"] - expect["duration"]) <= tol,
        f"{info['duration']:.3f} 秒（要求 {expect['duration']:.3f}，允许 ±{tol:.2f}）")
    add("有音轨", info["has_audio"], "有" if info["has_audio"] else "没有声音")
    if info["has_audio"]:
        for p in expect.get("voiceover", []):
            mid, span = p["start"] + 0.1, max(0.1, p["end"] - p["start"] - 0.2)
            db = _mean_db(out, mid, span)
            add(f"配音第{p['index'] + 1}句有声", db > -40, f"{p['start']:.2f}–{p['end']:.2f} 秒，"
                f"平均 {db:.1f} dB")
        lufs = _loudness(out)
        if lufs is not None:
            add("整体响度", -20 <= lufs <= -9, f"{lufs:.1f} LUFS（抖音建议 -16 ~ -12）")
    if expect.get("video_source"):
        same = _vhash(out) == _vhash(expect["video_source"])
        add("画面未改动", same, "与原片逐帧一致" if same else "画面和原片不一致")
    return {"ok": all(i["ok"] for i in items), "items": items}


def mux(spec: dict[str, Any], progress=lambda msg: None) -> dict[str, Any]:
    """只换声音、不动画面：视频流原样复制（-c:v copy，不重新编码），
    铺上 AI 配音和 BGM（人声出现时自动压低）。适合画面已经在别处做好的成片。
    spec: {video_id, voiceover?: {tts_id, at?, volume?}, bgm?: {name|url, volume?, fade_in?, fade_out?, start?},
           original_volume?=0（原片声音保留多少）, loudnorm?=true,
           speed?=1（整体变速 0.5~2：画面和配音一起加速、音调不变，BGM 保持原速铺满；
                     不为 1 时画面要重新编码）}"""
    import specs  # 延迟导入，避免循环引用
    specs.validate(spec, "mux")
    video_id = spec["video_id"]
    d = video_dir(video_id)
    meta = load_meta(video_id)
    src = d / meta["source"]
    total = float(meta["duration"])
    speed = float(spec.get("speed", 1.0))
    sped = abs(speed - 1.0) > 1e-3
    final = total / speed  # 变速后的成片时长
    tempo = f",atempo={speed:.4f}" if sped else ""  # atempo 变速不变调
    vo = spec.get("voiceover") or None
    bgm = spec.get("bgm") or None
    ovol = float(spec.get("original_volume", 0.0))
    if not vo and not bgm and not (ovol > 0 and meta["has_audio"]):
        raise EditorError("mux 至少需要 voiceover、bgm 或保留原声其中之一")
    out_id = uuid.uuid4().hex[:12]
    work = OUTPUTS / f".work_{out_id}"
    work.mkdir()
    try:
        inputs = ["-i", str(src)]
        nin = 1
        fc: list[str] = []
        mix: list[str] = []
        placed: list[dict] = []
        norm = ",loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" if spec.get("loudnorm", True) else ""
        if vo:
            import tts  # 延迟导入，避免循环引用
            progress("铺配音")
            track = work / "voiceover.wav"
            placed = tts.build_voice_track(vo["tts_id"], vo.get("at"), total, track)
            inputs += ["-i", str(track)]
            fc.append(f"[{nin}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={float(vo.get('volume', 1.0))}{tempo}{norm}[voice]")
            nin += 1
            mix.append("[voice]")
        if ovol > 0 and meta["has_audio"]:
            fc.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={ovol}{tempo}[orig]")
            mix.append("[orig]")
        if bgm:
            bpath = MUSIC / Path(bgm["name"]).name if bgm.get("name") else None
            if bgm.get("url"):
                bpath = MUSIC / import_music(bgm["url"], bgm.get("save_as", f"bgm_{out_id}"))
            if not bpath or not bpath.exists():
                raise EditorError(f"找不到背景音乐 {bgm}")
            fo, fi = float(bgm.get("fade_out", 1.5)), float(bgm.get("fade_in", 0.5))
            inputs += ["-stream_loop", "-1", "-ss", f"{float(bgm.get('start', 0)):.2f}", "-i", str(bpath)]
            fc.append(f"[{nin}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={float(bgm.get('volume', 0.12))},atrim=0:{final:.3f},afade=t=in:d={fi},"
                      f"afade=t=out:st={max(0, final - fo):.3f}:d={fo}[bgm]")
            nin += 1
            if mix:  # 有人声时 BGM 自动避让
                key = mix[0]
                fc.append(f"{key}asplit=2[k1][k2]")
                fc.append("[bgm][k2]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=350[bd]")
                mix = ["[k1]", *mix[1:], "[bd]"]
            else:
                mix = ["[bgm]"]
        progress("合成声音")
        if len(mix) > 1:
            fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,"
                      f"alimiter=limit=0.97,apad,atrim=0:{final:.3f}[a]")
        else:
            fc.append(f"{mix[0]}apad,atrim=0:{final:.3f}[a]")
        if sped:  # 变速：画面按 speed 加快并重新编码，帧率保持原片
            placed = [{**p, "start": p["start"] / speed, "end": p["end"] / speed} for p in placed]
            fps = meta.get("fps") or "30"
            fc.append(f"[0:v]setpts=PTS/{speed:.4f}[v]")
            vmap = ["-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-r", str(fps)]
        else:
            vmap = ["-map", "0:v:0", "-c:v", "copy"]
        out = OUTPUTS / f"{out_id}.mp4"
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
             *vmap, "-map", "[a]", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", "-t", f"{final:.3f}", "-movflags", "+faststart", str(out)])
        progress("成片自检")
        checks = verify_output(out, {"duration": final, "voiceover": placed,
                                     "video_source": None if sped else src})
        result = {"output_id": out_id, "file": out.name, "duration": round(final, 2),
                  "width": meta["width"], "height": meta["height"], "video_copied": not sped,
                  "speed": speed, "checks": checks,
                  "voiceover": [{"start": round(p["start"], 2), "end": round(p["end"], 2),
                                 "text": p["text"]} for p in placed], "captions": []}
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
