# 47 号 · 发布会

苹果发布会式的竖屏片子（1080×1920，30fps，无声）：黑色舞台、顶部聚光和浮尘、超大金属渐变字、数字滚动、「One more thing…」。适合新功能上线、新服务发布、网站宣传片开头。视觉和 openaigrowth 首页一致，强调色只用荧光青柠 `#C8FF00`。

## 怎么出片

```bash
python3 -I render.py plan spec.json                 # 打印每页起止秒数，按这个写配音
python3 -I render.py stills spec.json 2,4.5,13.5    # 检查图 still_<秒>.jpg
python3 -I render.py video spec.json out.mp4        # 整条
```

本机 Chrome 不是 Playwright 自带的那个时，设 `CHROME_PATH=/usr/bin/google-chrome`。码率上限 10M（H.264 High@4.1）。配音、音乐交给剪辑工具（`mux` / `render`），按所属方向固定的配音和模板来；先跑 `plan` 拿到每页的秒数再排配音。

## spec.json

照 `example.json` 改。最外层：`brand`（开场和结尾的大字标，默认 Shopwright）、`eyebrow`（开场小字，如「2026 · 跨境卖家发布会」）、`watermark`（可省，预览版用）、`scenes`。

开场页自动加在最前面；没写 `end` 会自动补一页结尾。每页都能写 `duration`（秒）覆盖默认时长。

| type | 默认秒数 | 字段 | 画面 |
|---|---|---|---|
| `intro`（自动） | 2.6 | — | 一道青柠光线划开，聚光灯亮起，字标逐字从模糊里升起 |
| `reveal` | 3.0 | `title` `sub` `image`（可省） | 产品面板 3D 转着落位（带地面倒影），大标题逐字升起、一道光扫过；`image` 写图片路径（相对 spec 文件），不写就画一个素材包界面示意 |
| `stat` | 1.9 | `eyebrow` `value` `unit` `prefix`（可省） `label` `note`（可省） `sample` | 超大数字从 0 滚到 `value`（小数照写），单位弹出 |
| `quote` | 2.6 | `text`（`[[关键词]]` 变绿） `who` `meta` `sample` | 青柠大引号弹出，原话大字 |
| `onemore` | 3.0 | `text`（默认 One more thing…） `eyebrow` `title` `sub` | 斜体小字淡入淡出 → 冲击光环 → 新东西大字砸出来 |
| `end` | 2.4 | `cta` `sub` | 字标 + 青柠网址按钮 |

除开场和结尾，底部有进度格（每页一格）。

## 内容规矩

- 数字和原话必须是真的。`stat`、`quote` 写 `sample: true` 会在画面上标「示例」，只给 Tony 看效果；正式版全部换成核对过的内容，`sample` 去掉，`watermark` 删掉。
- 不写没兑现的承诺（销量、过审、收入），不放价格（价格以网站为准）。
- 主要内容在 y 300~1360，进度格在 1440，1600 以下不放东西（平台按钮）。
