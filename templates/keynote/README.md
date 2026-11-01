# 47 号 · 发布会（v3「一根线」）

苹果发布会式的竖屏产品片（1080×1920，30fps，无声，约 20~25 秒）。整部片子只讲一件事：一件空白的衣服，怎么变成只属于一个人的。

**视觉规则**：全片黑白灰，唯一的颜色是那根青柠绣线 `#C8FF00`。开场它在黑暗里一针针走出来，中间在衣服上用缎面绣绣出名字（镜头微距跟着针走，绣完拉远），之后给关键词缝下划线，结尾在网址下面收针打结。别的地方不要再用青柠色。字用 Noto Sans CJK Medium、靠左、大留白，主句白、补充句灰。时长都是 0.5 秒的倍数（120 BPM 一拍），配乐按 120 拍选，转场落在拍子上。

## 怎么出片

```bash
python3 -I render.py plan spec.json                 # 打印每页起止秒数，按这个写配音
python3 -I render.py stills spec.json 2,4.5,13.5    # 检查图 still_<秒>.jpg
python3 -I render.py video spec.json out.mp4        # 整条
```

本机 Chrome 不是 Playwright 自带的那个时，设 `CHROME_PATH=/usr/bin/google-chrome`。码率上限 10M（H.264 High@4.1）。配音、音乐交给剪辑工具（`mux` / `render`），按所属方向固定的配音和模板来；先跑 `plan` 拿到每页的秒数再排配音。

## spec.json

照 `example.json` 改。最外层：`brand`（开场和结尾的大字标，默认 Shopwright）、`eyebrow`（开场小字，如「2026 · 跨境卖家发布会」）、`watermark`（可省，预览版用）、`scenes`。

开场页（`thread`）自动加在最前面；没写 `end` 会自动补一页结尾。每页可写 `duration` 覆盖默认时长。图片路径相对 spec 文件，要透明底抠图；`assets/` 里有现成白坯（卫衣、T 恤、帽子、毛毯、圆领卫衣，来自网站，Codex 生成）和绣名字用的草书字体 Pacifico（OFL 授权）。名字由 render.py 用 fontTools 提出字形，只支持英文字母。

| type | 默认秒数 | 字段 | 画面 |
|---|---|---|---|
| `thread`（自动） | 3.5 | 用最外层 `brand` `eyebrow` | 黑暗里一根绣线一针针从左边走进来，划过画面，字标从遮罩里升起 |
| `statement` | 2.5 | `lines`（每行一项，`{词}` 会被缝下划线）`bright`（从第几行起变灰，0 开始）`label` `who` `sample` `top` | 大字逐行升起；写了 `who` 就是客户原话（带出处，`sample` 标示例） |
| `stitch` | 5 | `image` `name` `at`（名字中心在图上的位置 [x,y] 比例）`width`（名字宽度占图宽比例）`height` `title` `caption` | 镜头 3 倍微距对着衣服，针一针针缎面绣出名字、镜头跟着针走，绣完拉远看到整件 |
| `montage` | 每件 0.75 | `lines` `items`：`[{image, name, at, width, height, label}]` | 一件件产品甩镜切换，每件上绣着不同名字 |
| `stat` | 2.5 | `label` `value` `unit` `note` `sample` | 超大数字靠左升起，下面缝一道线 |
| `family` | 3 | `lines` `items`（4 件，同上） | 2×2 全家福，每件绣着名字，镜头慢推 |
| `end` | 3.5 | `cta` `sub` | 网址升起，绣线在下面缝过去、打一个结 |

## 内容规矩

- 数字和原话必须是真的。`stat`、`quote` 写 `sample: true` 会在画面上标「示例」，只给 Tony 看效果；正式版全部换成核对过的内容，`sample` 去掉，`watermark` 删掉。
- 不写没兑现的承诺（销量、过审、收入），不放价格（价格以网站为准）。
- 主要内容在 y 180~1500，1600 以下不放东西（平台按钮）。
- 产品图换成实拍时，用去掉背景的 PNG/WebP，不然没有倒影和投影。
