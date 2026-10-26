"""从原片或成片抽帧，生成 Noto Sans CJK 大字封面。"""
from __future__ import annotations

import io
import re
import subprocess
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import editor
import specs


def cover_path(cover_id: str) -> Path:
    if not isinstance(cover_id, str) or not re.fullmatch(r"[a-z0-9]{12}", cover_id):
        raise editor.EditorError("cover_id 格式不对，请使用 make_cover 返回的编号")
    path = editor.DATA_DIR / "covers" / f"{cover_id}.png"
    if not path.exists():
        raise editor.EditorError(f"找不到封面 {cover_id}，请先调用 make_cover")
    return path


def validate(spec: dict) -> tuple[Path, dict]:
    specs.validate(spec, "cover")
    if not spec["title"].strip() or len(spec["title"]) > 60:
        raise editor.EditorError("title 需要 1–60 个字符，最多两行")
    if len(spec["title"].splitlines()) > 2 or any(not s.strip() for s in spec["title"].splitlines()):
        raise editor.EditorError("title 最多两行，不能有空行")
    if len(spec.get("subtitle", "")) > 120:
        raise editor.EditorError("subtitle 最多 120 个字符，请精简副标题")
    for word in spec.get("style", {}).get("highlight", []):
        if not word.strip() or word not in spec["title"]:
            raise editor.EditorError("style.highlight 每项需要是标题中已有的非空词语")
    if spec.get("video_id"):
        meta = editor.load_meta(spec["video_id"])
        path = editor.video_dir(spec["video_id"]) / meta["source"]
    else:
        editor.load_output(spec["output_id"])
        path = editor.OUTPUTS / f"{spec['output_id']}.mp4"
        meta = editor.probe(path)
    if spec["time"] >= meta["duration"]:
        raise editor.EditorError(f"time 必须小于视频时长 {meta['duration']:.2f} 秒")
    return path, meta


def _font(size: int) -> ImageFont.FreeTypeFont:
    # 使用安装脚本提供的 Noto CJK；不在线下载或用缺中文字形的字体兜底。
    try:
        match = subprocess.run(["fc-match", "-f", "%{file}|%{index}", "Noto Sans CJK SC:style=Bold"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        path, index = match.split("|")
        if "NotoSansCJK" in Path(path).name:
            return ImageFont.truetype(path, size, index=int(index))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    candidates = sorted(Path(editor.FONTS_DIR).rglob("NotoSansCJK*"))
    for path in sorted(candidates, key=lambda p: ("Bold" not in p.name, "sc" not in p.name.lower())):
        if path.suffix.lower() in (".ttc", ".otf", ".ttf"):
            return ImageFont.truetype(str(path), size)
    raise editor.EditorError("未找到 Noto Sans CJK 字体，请安装 fonts-noto-cjk 或放入 FONTS_DIR")


def _lines(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines = []
    for paragraph in text.splitlines():
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return lines


def make(spec: dict, progress=lambda msg: None) -> dict:
    path, meta = validate(spec)
    progress("提取封面帧并转换 HDR 色彩")
    color = editor._color_filter(meta, {})
    vf = color + "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(spec["time"]), "-i", str(path),
                        "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-c:v", "png", "-"],
                       capture_output=True, timeout=120)
    if p.returncode or not p.stdout:
        raise editor.EditorError("抽取封面失败，请换一个 time 或检查视频：" + p.stderr.decode(errors="ignore")[-1000:])
    image = Image.open(io.BytesIO(p.stdout)).convert("RGB")
    progress("排版封面标题")
    title = spec["title"].strip()
    for size in range(140, 71, -4):
        font = _font(size)
        lines = _lines(title, font, 940)
        if len(lines) <= 2:
            break
    else:
        raise editor.EditorError("标题无法在两行大字中放下，请减少文字或调整换行")
    style = spec.get("style", {})
    highlights = set()
    flat = title.replace("\n", "").replace("\r", "")
    for word in style.get("highlight", []):
        for match in re.finditer(re.escape(word), flat):
            highlights.update(range(match.start(), match.end()))
    draw = ImageDraw.Draw(image)
    y = int(1920 * style.get("y", 0.20))
    cursor = 0
    for line in lines:
        x = (1080 - font.getlength(line)) / 2
        for i, char in enumerate(line):
            draw.text((x + font.getlength(line[:i]), y), char, font=font, anchor="lt",
                      fill="#FFE033" if cursor + i in highlights else "white",
                      stroke_width=7, stroke_fill="black")
        cursor += len(line)
        y += int(size * 1.3)
    subtitle = spec.get("subtitle", "").strip()
    if subtitle:
        subfont = _font(52)
        for line in _lines(subtitle, subfont, 940):
            if y + 70 > 1850:
                raise editor.EditorError("副标题超出画面，请精简文字或减小 style.y")
            draw.text(((1080 - subfont.getlength(line)) / 2, y + 15), line, font=subfont,
                      anchor="lt", fill="white", stroke_width=4, stroke_fill="black")
            y += 70
    if y > 1850:
        raise editor.EditorError("标题超出画面，请减小 style.y")
    ident = uuid.uuid4().hex[:12]
    out = editor.DATA_DIR / "covers" / f"{ident}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return {"cover_id": ident, "file": out.name, "width": 1080, "height": 1920}
