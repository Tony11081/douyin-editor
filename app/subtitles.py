"""按成片时间轴导出 UTF-8 SRT / WebVTT，不重新转写或猜测译文。"""
from __future__ import annotations

import math
import uuid

import editor


def _cues(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        try:
            start, end, text = row["start"], row["end"], row["text"]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   for v in (start, end)) or start < 0 or end <= start or not isinstance(text, str):
                raise ValueError
            text = " ".join(text.split())
            if not text or round(end * 1000) <= round(start * 1000):
                raise ValueError
            result.append({"start": start, "end": end, "text": text})
        except (KeyError, TypeError, ValueError) as e:
            raise editor.EditorError("成片字幕时间或文字无效，请重新 render 后导出") from e
    return sorted(result, key=lambda c: (c["start"], c["end"]))


def _bilingual(captions: list[dict], subs: list[dict]) -> list[dict]:
    result = []
    for cue in captions:
        matching = [s for s in subs if s["start"] < cue["end"] and s["end"] > cue["start"]]
        points = sorted({cue["start"], cue["end"], *[max(cue["start"], s["start"]) for s in matching],
                         *[min(cue["end"], s["end"]) for s in matching]})
        for start, end in zip(points, points[1:]):
            active = [s for s in matching if s["start"] <= start and s["end"] >= end]
            if len(active) != 1:
                raise editor.EditorError(f"{start:.3f}–{end:.3f} 秒没有唯一对应的译文，请补齐或消除 subs 重叠后重新 render")
            result.append({"start": start, "end": end, "text": cue["text"] + "\n" + active[0]["text"]})
    return result


def _stamp(seconds: float, fmt: str) -> str:
    millis = round(seconds * 1000)
    minutes, sec = divmod(millis // 1000, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02}:{minute:02}:{sec:02}{',' if fmt == 'srt' else '.'}{millis % 1000:03}"


def export(output_id: str, format: str = "srt", bilingual: bool = False) -> dict:
    if format not in ("srt", "vtt") or not isinstance(bilingual, bool):
        raise editor.EditorError('format 只能是 "srt" 或 "vtt"；bilingual 必须是 true/false')
    meta = editor.load_output(output_id)
    captions = _cues(meta.get("captions") or [])
    if not captions:
        raise editor.EditorError("成片没有可导出的字幕；请先带字幕 render。mux 请直接传 render 的 output_id，导入的视频无法可靠还原字幕时间")
    if bilingual:
        captions = _bilingual(captions, _cues(meta.get("subs") or []))
    blocks = []
    for i, cue in enumerate(captions, 1):
        text = cue["text"]
        if format == "vtt":
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        blocks.append(f"{i}\n{_stamp(cue['start'], format)} --> {_stamp(cue['end'], format)}\n{text}")
    body = ("WEBVTT\n\n" if format == "vtt" else "") + "\n\n".join(blocks) + "\n"
    folder = editor.DATA_DIR / "subtitles"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{output_id}{'_bilingual' if bilingual else ''}.{format}"
    tmp = folder / f".{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(folder / filename)
    finally:
        tmp.unlink(missing_ok=True)
    return {"output_id": output_id, "file": filename, "format": format, "bilingual": bilingual,
            "count": len(captions)}
