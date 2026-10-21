"""AI 配音：调用 OpenRouter 的语音接口（兼容 OpenAI /audio/speech），按句生成旁白。

密钥放在服务器 .env 的 OPENROUTER_API_KEY 里，不经过对话。
每次配音存在 DATA_DIR/tts/<tts_id>/：每句一个 wav，外加 meta.json（每句文字和时长）
和一条按顺序拼好的完整旁白 track.mp3（可下载试听）。
"""
from __future__ import annotations

import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

import editor
from editor import EditorError, run

API_BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
DEFAULT_MODEL = os.environ.get("OPENROUTER_TTS_MODEL", "openai/gpt-4o-mini-tts-2025-12-15")
DEFAULT_VOICE = os.environ.get("OPENROUTER_TTS_VOICE", "")
TTS_DIR = editor.DATA_DIR / "tts"
TTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_CHARS = 600          # 单句上限，太长的旁白请按句拆开传


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        raise EditorError("服务器还没配置 OPENROUTER_API_KEY：在 .env 里加一行 "
                          "OPENROUTER_API_KEY=sk-or-...，然后 systemctl restart douyin-editor")
    return k


def tts_dir(tts_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9]{12}", tts_id or ""):
        raise EditorError("tts_id 格式不对")
    d = TTS_DIR / tts_id
    if not (d / "meta.json").exists():
        raise EditorError(f"找不到配音 {tts_id}")
    return d


def load(tts_id: str) -> dict[str, Any]:
    return json.loads((tts_dir(tts_id) / "meta.json").read_text())


def _duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip() or 0)


def _speak(text: str, model: str, voice: str, instructions: str | None,
           speed: float | None, provider: dict | None) -> bytes:
    body: dict[str, Any] = {"model": model, "input": text, "response_format": "mp3"}
    if voice:
        body["voice"] = voice
    if instructions:
        body["instructions"] = instructions
    if speed and abs(float(speed) - 1.0) > 1e-3:
        body["speed"] = float(speed)
    if provider:
        body["provider"] = provider
    last = ""
    for _ in range(3):  # 网络抖动或限流时重试
        try:
            r = requests.post(f"{API_BASE}/audio/speech", json=body, timeout=180, headers={
                "Authorization": f"Bearer {_key()}",
                "HTTP-Referer": os.environ.get("PUBLIC_URL", "http://localhost"),
                "X-Title": "douyin-editor"})
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
            continue
        ctype = r.headers.get("Content-Type", "")
        if r.status_code == 200 and "json" not in ctype and len(r.content) > 500:
            return r.content
        try:
            err = r.json().get("error", r.text)
        except ValueError:
            err = r.text
        last = f"HTTP {r.status_code}: {str(err)[:600]}"
        if r.status_code in (400, 401, 402, 403, 404):
            break  # 参数、余额、权限问题，重试没用
    raise EditorError(f"配音失败（{model} / {voice or '默认音色'}）：{last}")


_DIGITS = str.maketrans("0123456789", "零一二三四五六七八九")


def _norm(t: str) -> str:
    t = editor._to_simplified(t).lower().translate(_DIGITS)
    t = t.replace("%", "百分之").replace("两", "二")
    return "".join(ch for ch in t if ch not in editor.PUNCT and not ch.isspace())


def check_segments(meta: dict[str, Any], threshold: float = 0.8) -> dict[str, Any]:
    """用 Whisper 听一遍每句配音，和原文比对，找出可能念错、漏念、多念的句子。"""
    import difflib
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return {"status": "skipped", "reason": "服务器没装 faster-whisper，无法核对"}
    d = TTS_DIR / meta["tts_id"]
    out, bad = [], []
    for it in meta["segments"]:
        heard = editor.whisper_file(d / it["file"])
        score = difflib.SequenceMatcher(None, _norm(it["text"]), _norm(heard)).ratio()
        row = {"index": it["index"], "score": round(score, 2), "heard": heard}
        out.append(row)
        if score < threshold:
            bad.append(it["index"])
    return {"status": "ok" if not bad else "needs_review", "threshold": threshold,
            "flagged": bad, "segments": out,
            "note": "flagged 里的句子可能念错/漏念，请试听；数字、英文的读法差异也可能被标出"}


def synthesize(segments: list[str], model: str | None = None, voice: str | None = None,
               instructions: str | None = None, speed: float | None = None,
               gap: float = 0.3, trim: bool = True, provider: dict | None = None,
               verify: bool = True) -> dict[str, Any]:
    """逐句生成配音。返回每句的时长，以及按 gap 间隔顺排时每句在旁白里的起止时间。"""
    segs = [s.strip() for s in segments if s and s.strip()]
    if not segs:
        raise EditorError("没有要配音的文字")
    for s in segs:
        if len(s) > MAX_CHARS:
            raise EditorError(f"单句太长（{len(s)} 字），请拆成多句：{s[:30]}…")
    model = model or DEFAULT_MODEL
    voice = voice if voice is not None else DEFAULT_VOICE
    tid = uuid.uuid4().hex[:12]
    d = TTS_DIR / tid
    d.mkdir(parents=True)

    def one(k: int) -> dict[str, Any]:
        raw = d / f"raw_{k:03d}.mp3"
        raw.write_bytes(_speak(segs[k], model, voice, instructions, speed, provider))
        wav = d / f"seg_{k:03d}.wav"
        af = "aresample=48000,aformat=channel_layouts=stereo"
        if trim:  # 去掉每句首尾的静音，时长才准，方便对画面
            af += (",silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
                   "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,"
                   "areverse")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", af, "-c:a", "pcm_s16le", str(wav)])
        raw.unlink(missing_ok=True)
        dur = _duration(wav)
        if dur < 0.15:
            raise EditorError(f"第 {k + 1} 句生成的音频是空的：{segs[k][:30]}")
        return {"index": k, "text": segs[k], "file": wav.name, "duration": round(dur, 3)}

    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            items = list(ex.map(one, range(len(segs))))
        t = 0.0
        for it in items:
            it["start"] = round(t, 3)
            it["end"] = round(t + it["duration"], 3)
            t = it["end"] + gap
        total = items[-1]["end"]
        # 拼一条完整旁白供试听
        track = d / "track.mp3"
        inputs, fc = [], []
        for k, it in enumerate(items):
            inputs += ["-i", str(d / it["file"])]
            ms = int(it["start"] * 1000)
            fc.append(f"[{k}:a]adelay={ms}|{ms}[d{k}]")
        fc.append("".join(f"[d{k}]" for k in range(len(items))) +
                  f"amix=inputs={len(items)}:duration=longest:normalize=0,"
                  f"loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total + 0.3:.3f}[a]")
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
             "-map", "[a]", "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k", str(track)])
    except Exception:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        raise
    meta = {"tts_id": tid, "model": model, "voice": voice, "instructions": instructions,
            "speed": speed, "gap": gap, "total": round(total, 3), "segments": items,
            "track": track.name}
    if verify:
        try:
            meta["verify"] = check_segments(meta)
        except Exception as e:  # noqa: BLE001  核对失败不影响配音本身
            meta["verify"] = {"status": "error", "reason": f"{type(e).__name__}: {e}"[:300]}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta


def plan_voice(tts_id: str, at: list[float] | None, total: float) -> list[dict]:
    """算出每句配音在成片里的位置并严格检查：句数对不上、超出成片、句子互相重叠都直接报错，
    不会悄悄丢句或截断。"""
    meta = load(tts_id)
    items = meta["segments"]
    if at is not None:
        if len(at) != len(items):
            raise EditorError(f"voiceover.at 有 {len(at)} 个时间，但配音有 {len(items)} 句")
        starts = [float(x) for x in at]
    else:
        starts = [float(it["start"]) for it in items]
    placed = []
    for k, (it, s) in enumerate(zip(items, starts)):
        e = s + float(it["duration"])
        if e > total + 0.05:
            raise EditorError(f"第 {k + 1} 句配音（{s:.2f}–{e:.2f} 秒）超出成片时长 {total:.2f} 秒，"
                              f"会被截断：把 at 提前，或把画面加长")
        if placed and s < placed[-1]["end"] - 0.02:
            raise EditorError(f"第 {k + 1} 句配音从 {s:.2f} 秒开始，但第 {k} 句要到 "
                              f"{placed[-1]['end']:.2f} 秒才结束，两句会重叠")
        placed.append({"index": k, "text": it["text"], "start": s, "end": min(e, total),
                       "file": it["file"]})
    return placed


def build_voice_track(tts_id: str, at: list[float] | None, total: float, out: Path) -> list[dict]:
    """把配音的每句放到成片时间轴上，输出一条和成片等长的 wav。返回每句的位置（给字幕用）。"""
    d = tts_dir(tts_id)
    placed = plan_voice(tts_id, at, total)
    inputs, fc = [], []
    for n, p in enumerate(placed):
        inputs += ["-i", str(d / p["file"])]
        ms = max(0, int(round(p["start"] * 1000)))
        fc.append(f"[{n}:a]adelay={ms}|{ms}[d{n}]")
    n = len(placed)
    fc.append("".join(f"[d{k}]" for k in range(n)) +
              f"amix=inputs={n}:duration=longest:normalize=0,apad,atrim=0:{total:.3f}[a]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[a]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(out)])
    return placed


def list_voices(filter_text: str | None = None) -> list[dict[str, Any]]:
    """列出 OpenRouter 上能输出语音的模型、价格和可用音色。"""
    r = requests.get(f"{API_BASE}/models", params={"output_modalities": "speech"}, timeout=60)
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        mods = ((m.get("architecture") or {}).get("output_modalities") or [])
        if mods and "speech" not in mods and "audio" not in mods:
            continue
        text = f"{m.get('id', '')} {m.get('name', '')} {m.get('description', '')}"
        if filter_text and filter_text.lower() not in text.lower():
            continue
        out.append({"id": m.get("id"), "name": m.get("name"),
                    "pricing": m.get("pricing"),
                    "supported_voices": m.get("supported_voices"),
                    "supported_parameters": m.get("supported_parameters"),
                    "description": (m.get("description") or "")[:300]})
    return out


def preview(tts_id: str) -> Path:
    return tts_dir(tts_id) / load(tts_id)["track"]


if __name__ == "__main__":  # 手动试听：python3 tts.py "第一句" "第二句"
    import sys
    print(json.dumps(synthesize(sys.argv[1:]), ensure_ascii=False, indent=1))
