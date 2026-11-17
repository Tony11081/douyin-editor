"""把 pack.html 渲染出的透明 webm + 实拍素材，拼成剪辑服务器 render 用的 spec（叠素材窗）。

用法：
  python3 -I compose.py plan.json > spec.json

plan.json：
{
  "width": 1080, "height": 1920,
  "slots": {                      # 素材槽 → 剪辑服务器视频库里的视频
    "P": {"video_id": "374646221bc8", "w": 720, "h": 1280, "from": 0.5},
    "L": {"video_id": "d363bf39d3b7", "w": 1280, "h": 720}
  },
  "parts": [                      # 按成片顺序；一段 = 一个模板
    {"meta": "samples/65_sk.meta.json", "webm": "https://raw.githubusercontent.com/.../65_sk.webm",
     "slots": {"P": {"from": 2}}}  # 可选：这段里某个槽换起点/换视频
  ]
}

注意：一个模板里有两个素材窗（75、77 号）时，素材宽高比要接近窗口（横窗用横屏素材），否则铺满后的溢出会盖住另一个窗，compose.py 会报警告。

做法：每个素材窗按「铺满（cover）+ 推近 zoom + 取景 fx/fy」算出缩放后的尺寸和位置，
作为 layer:"base" 叠加层铺在底下；模板透明层（挖空了素材窗）作为 layer:"front" 盖在上面，
所以素材只从窗里透出来，模板的暗角、颗粒、字都压在素材上。
"""
import json, sys, pathlib


def cover(win, src):
    s = max(win["w"] / src["w"], win["h"] / src["h"]) * float(win.get("zoom", 1))
    ow = int(round(src["w"] * s / 2)) * 2
    oh = int(round(src["h"] * s / 2)) * 2
    ox = win["x"] - (ow - win["w"]) * float(win.get("fx", .5))
    oy = win["y"] - (oh - win["h"]) * float(win.get("fy", .5))
    return int(round(ox)), int(round(oy)), ow, oh


def build(plan, base_dir):
    W, H = plan.get("width", 1080), plan.get("height", 1920)
    clips, overlays, at = [], [], 0.0
    first = next(iter(plan["slots"].values()))
    for part in plan["parts"]:
        meta = json.loads((base_dir / part["meta"]).read_text())
        dur = float(meta["dur"])
        slots = {k: {**v, **part.get("slots", {}).get(k, {})} for k, v in plan["slots"].items()}
        # 底层占位：任意一条素材，时长等于这段（会被模板和素材窗盖住）
        b = part.get("base", first)
        clips.append({"video_id": b["video_id"], "start": float(b.get("from", 0)), "end": float(b.get("from", 0)) + dur})
        segs = meta["segments"]
        for i, seg in enumerate(segs):
            t0 = float(seg["t"]); t1 = float(segs[i + 1]["t"]) if i + 1 < len(segs) else dur
            for win in seg["wins"]:
                src = slots[win["slot"]]
                x, y, w, h = cover(win, src)
                # 同时有两个素材窗时，铺满后溢出的部分不能伸进另一个窗（会盖住那个窗的素材）
                for o in seg["wins"]:
                    if o is not win and x < o["x"] + o["w"] and o["x"] < x + w and y < o["y"] + o["h"] and o["y"] < y + h:
                        print(f"警告：{meta['tpl']} 的 {win['slot']} 素材铺满后伸进了 {o['slot']} 窗，"
                              f"换一条宽高比更接近窗口的素材（例如横屏窗用横屏素材）", file=sys.stderr)
                overlays.append({"video_id": src["video_id"], "start": round(at + t0, 3),
                                 "from": round(float(src.get("from", 0)) + t0, 3), "duration": round(t1 - t0, 3),
                                 "x": x, "y": y, "w": w, "h": h, "layer": "base"})
        overlays.append({"url": part["webm"], "start": round(at, 3), "duration": dur,
                         "x": 0, "y": 0, "w": W, "h": H, "layer": "front"})
        at += dur
    return {"video_id": first["video_id"], "clips": clips, "captions": "none",
            "effects": {"drift": 0, "flash_first": False, "sfx": False, "progress_bar": False},
            "overlays": overlays, "width": W, "height": H}


if __name__ == "__main__":
    p = pathlib.Path(sys.argv[1])
    print(json.dumps(build(json.loads(p.read_text()), pathlib.Path(__file__).parent), ensure_ascii=False, indent=1))
