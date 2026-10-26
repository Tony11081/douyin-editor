"""剪辑方案（spec）严格校验：写错的参数名、类型不对、超出范围的值一律报错并给出改法，
不再静默忽略或偷偷改值。目的是让工具对每一条指令要么精确执行、要么明确拒绝。"""
from __future__ import annotations

import difflib
import math
import re
from typing import Any

from editor import EditorError

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


# 类型描述：("num", lo, hi) / ("int", lo, hi) / "str" / "bool" / "color" / ("enum", [...])
# / ("list", item) / ("map", key, value) / dict（嵌套对象）/ ("any_of", a, b)
def num(lo=None, hi=None):
    return ("num", lo, hi)


def integer(lo=None, hi=None):
    return ("int", lo, hi)


def enum(*vals):
    return ("enum", list(vals))


def lst(item, max_len=None):
    return ("list", item, max_len)


def mapping(k, v):
    return ("map", k, v)


CLIP = {"start": num(0), "end": num(0), "zoom": num(1.0, 3.0), "text": "str", "focus_y": num(0, 1),
        "sub": ("any_of", "str", lst("str")),
        "drift": num(0, 0.5), "flash": "bool", "video_id": "str"}
CAPTION_STYLE = {"preset": enum("douyin", "box", "yellow"), "font_size": integer(10, 400), "y": num(0.05, 0.98),
                 "max_chars": integer(4, 30), "color": "color", "highlight_color": "color",
                 "outline_color": "color", "outline": integer(0, 40), "outline_ratio": num(0, 0.3),
                 "shadow": integer(0, 30), "box": "bool", "size_ratio": num(0.02, 0.3), "font": "str",
                 "highlight_scale": integer(50, 200),
                 "sub_size_ratio": num(0.02, 0.2), "sub_font_size": integer(10, 300), "sub_color": "color",
                 "sub_outline_color": "color", "sub_position": enum("below", "above"),
                 "sub_gap": integer(0, 300), "sub_font": "str"}
TITLE = {"text": "str", "duration": num(0.1), "y": num(0, 0.9), "font_size": integer(10, 400),
         "color": "color", "color2": "color", "outline_color": "color"}
BGM = {"name": "str", "url": "str", "volume": num(0, 2), "fade_in": num(0, 30), "fade_out": num(0, 30),
       "start": num(0), "save_as": "str"}
AUDIO = {"denoise": "bool", "loudnorm": "bool"}
EFFECTS = {"drift": num(0, 0.5), "oversample": num(1, 3), "flash_first": "bool", "sfx": "bool",
           "sfx_volume": num(0, 2), "progress_bar": "bool", "bar_color": "color", "bar_height": integer(1, 60)}
COLOR = {"mode": enum("auto", "sdr", "hdr"), "npl": num(10, 1000),
         "tonemap": enum("mobius", "hable", "reinhard", "clip", "linear", "gamma"), "param": num(),
         "desat": num(0, 10), "brightness": num(-1, 1), "contrast": num(0, 3), "saturation": num(0, 3),
         "gamma": num(0.1, 10), "warmth": num(-1, 1)}
OVERLAY = {"url": "str", "video_id": "str", "start": num(0), "from": num(0), "duration": num(0.1),
           "x": integer(), "y": integer(), "w": integer(16, 4096), "h": integer(16, 4096),
           "fade": num(0, 5), "layer": enum("front", "behind", "base")}
VOICEOVER = {"tts_id": "str", "at": lst(num(0)), "volume": num(0, 3), "original_volume": num(0, 3),
             "subs": lst("str")}
COVER = {"cover_id": "str", "duration": num(0.01)}
MAKE_COVER = {"video_id": "str", "output_id": "str", "time": num(0), "title": "str", "subtitle": "str",
              "style": {"highlight": lst("str"), "y": num(0, 0.8)}}

RENDER = {"video_id": "str", "clips": lst(CLIP), "captions": enum("auto", "none", "voiceover"),
          "corrections": mapping("str", "str"), "highlight_words": lst("str"),
          "caption_style": CAPTION_STYLE, "title": TITLE, "bgm": BGM, "audio": AUDIO,
          "width": integer(240, 4096), "height": integer(240, 4096), "fps": integer(10, 60),
          "focus_y": num(0, 1), "shift_y": integer(0, 1800), "shift_color": "color", "color": COLOR, "effects": EFFECTS, "overlays": lst(OVERLAY),
          "matte": {"feather": num(0, 20)}, "voiceover": VOICEOVER, "cover": COVER,
          "preset": enum("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower")}
MUX = {"video_id": "str", "output_id": "str", "voiceover": {"tts_id": "str", "at": lst(num(0)), "volume": num(0, 3)},
       "bgm": BGM, "original_volume": num(0, 3), "loudnorm": "bool", "speed": num(0.5, 2)}
REQUIRED = {"render": {"video_id"}, "mux": set(), "cover": {"title", "time"}}
NESTED_REQUIRED = {"title": {"text"}, "voiceover": {"tts_id"}, "cover": {"cover_id"}}


def _tname(t) -> str:
    if isinstance(t, dict):
        return "对象"
    if t in ("str", "bool", "color"):
        return {"str": "文字", "bool": "true/false", "color": "#RRGGBB 颜色"}[t]
    k = t[0]
    if k in ("num", "int"):
        lo, hi = t[1], t[2]
        rng = "" if lo is None and hi is None else f"（{'' if lo is None else lo}~{'' if hi is None else hi}）"
        return ("数字" if k == "num" else "整数") + rng
    if k == "enum":
        return "其中之一：" + " / ".join(map(str, t[1]))
    if k == "list":
        return "列表"
    if k == "map":
        return "{键: 值} 对象"
    return str(t)


def _check(v: Any, t, path: str, errs: list[str]) -> None:
    if isinstance(t, dict):
        if not isinstance(v, dict):
            errs.append(f"{path} 应该是对象，现在是 {type(v).__name__}")
            return
        for k, val in v.items():
            if k not in t:
                near = difflib.get_close_matches(k, list(t), n=1, cutoff=0.5)
                hint = f"，你是不是想写 {near[0]}？" if near else f"；可用参数：{', '.join(t)}"
                errs.append(f"{path}.{k} 是不认识的参数{hint}")
                continue
            _check(val, t[k], f"{path}.{k}", errs)
        base = path.split(".")[-1]
        base = re.sub(r"\[\d+\]$", "[]", base)
        for req in NESTED_REQUIRED.get(base, set()):
            if req not in v:
                errs.append(f"{path} 缺少必填项 {req}")
        return
    if v is None:
        errs.append(f"{path} 不能是 null（不需要就整项删掉）")
        return
    if t == "str":
        if not isinstance(v, str):
            errs.append(f"{path} 应该是文字")
    elif t == "bool":
        if not isinstance(v, bool):
            errs.append(f"{path} 应该是 true 或 false")
    elif t == "color":
        if not isinstance(v, str) or not COLOR_RE.match(v):
            errs.append(f"{path} 应该是 #RRGGBB 颜色，现在是 {v!r}")
    elif t[0] in ("num", "int"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) \
                or (t[0] == "int" and float(v) != int(v)):
            errs.append(f"{path} 应该是{_tname(t)}，现在是 {v!r}")
            return
        lo, hi = t[1], t[2]
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            errs.append(f"{path} = {v} 超出范围，应该是{_tname(t)}")
    elif t[0] == "enum":
        if v not in t[1]:
            errs.append(f"{path} = {v!r} 不支持，应该是{_tname(t)}")
    elif t[0] == "any_of":
        tried = []
        for alt in t[1:]:
            e2: list[str] = []
            _check(v, alt, path, e2)
            if not e2:
                return
            tried.append(_tname(alt))
        errs.append(f"{path} 应该是：{' 或 '.join(tried)}")
    elif t[0] == "list":
        if not isinstance(v, list):
            errs.append(f"{path} 应该是列表")
            return
        for i, it in enumerate(v):
            _check(it, t[1], f"{path}[{i}]", errs)
    elif t[0] == "map":
        if not isinstance(v, dict):
            errs.append(f"{path} 应该是 {{键: 值}} 对象")
            return
        for k, val in v.items():
            _check(k, t[1], f"{path} 的键", errs)
            _check(val, t[2], f"{path}[{k!r}]", errs)


def validate(spec: Any, kind: str) -> None:
    schema = {"render": RENDER, "mux": MUX, "cover": MAKE_COVER}[kind]
    errs: list[str] = []
    if not isinstance(spec, dict):
        raise EditorError("spec 应该是对象")
    for req in REQUIRED[kind]:
        if req not in spec:
            errs.append(f"缺少必填项 {req}")
    _check(spec, schema, "spec", errs)
    if kind in ("mux", "cover") and (bool(spec.get("video_id")) == bool(spec.get("output_id"))):
        errs.append("video_id 和 output_id 必须二选一，不能同时提供或都省略")
    if errs:
        raise EditorError("剪辑方案有问题，没有执行（请改好后重试）：\n- " + "\n- ".join(errs))
