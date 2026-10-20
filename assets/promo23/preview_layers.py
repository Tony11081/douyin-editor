"""本地分层预览：背景 → 背后大字 → 抠出的人物 → 前景层，和服务器的合成顺序一致。
用法: python3 preview_layers.py <ref.jpg> <t1,t2,...> <out.jpg>"""
import subprocess
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image

ref, times, out, V = sys.argv[1], [float(x) for x in sys.argv[2].split(",")], sys.argv[3], sys.argv[4]
W, H = 1080, 1920
bg = Image.open(ref).convert("RGB").resize((W, H), Image.LANCZOS)

# 抠像（单帧重复几次让递归状态收敛）
sess = ort.InferenceSession("/home/claude/matting/rvm_mobilenetv3_fp32.onnx", providers=["CPUExecutionProvider"])
small = np.asarray(bg.resize((W // 2, H // 2)), np.float32).transpose(2, 0, 1)[None] / 255
rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
for _ in range(6):
    fgr, pha, *rec = sess.run(None, {"src": small, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                     "downsample_ratio": np.array([0.5], np.float32)})
matte = Image.fromarray((np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)

ts = ",".join(f"{t}" for t in times)
for layer in ("behind", "front"):
    subprocess.run(["node", "render.mjs", "stills", ts], check=True, env={"LAYER": layer, "V": V, "PATH": "/usr/bin:/usr/local/bin:/opt/node22/bin"})

tiles = []
for t in times:
    comp = bg.copy().convert("RGBA")
    comp.alpha_composite(Image.open(f"stills/{V}_behind_{t:.2f}.png").convert("RGBA"))
    person = bg.convert("RGBA")
    person.putalpha(matte)
    comp.alpha_composite(person)
    comp.alpha_composite(Image.open(f"stills/{V}_front_{t:.2f}.png").convert("RGBA"))
    tiles.append(comp.convert("RGB").resize((270, 480), Image.LANCZOS))
sheet = Image.new("RGB", (270 * min(5, len(tiles)), 480 * ((len(tiles) + 4) // 5)))
for i, im in enumerate(tiles):
    sheet.paste(im, (270 * (i % 5), 480 * (i // 5)))
sheet.save(out, quality=88)
print("ok", out)
