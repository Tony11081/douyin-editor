# 给智能体看的：douyin-editor 使用说明

这个仓库是 Tony（Etsy-Tony / Shopwright）的抖音剪辑工具和**视频模板库**。Codex、Claude、Muse、Grok 等智能体接活做视频时，先读这一页，再读模板总表。

## 1. 先看哪里

| 要做什么 | 读这个 |
|---|---|
| 选模板（Tony 只说编号） | `templates/catalog/README.md`：1–79 号 + 51b 全在这张表，写了每个编号在哪个目录、哪个仓库 |
| 每天固定的几个方向（政策速递、网站宣传、知识点、AI浪潮…） | 同一页第一部分：每个方向的模板、配音、音乐都是固定的，不混用 |
| 64–79 号（创作者风格包、4:3 横版口播） | `templates/creator-pack/README.md` |
| 某个模板怎么出片 | 那个模板目录里的 `README.md` |
| 剪辑服务器本身（导入、转写、render、mux） | 仓库根目录 `README.md` 和 `app/` |

部分模板在另一个仓库 `Tony11081/video-drop` 的 `templates/`，总表里写了「video-drop」的就是。

## 2. 出片的通用流程

1. **模板出画面**：模板都是网页（1080×1920 / 30fps，79 号是 1440×1080），`render(t)` 逐帧画。
   - 检查图：各模板 `render.py stills ...`（64–79 号：`python3 -I templates/creator-pack/render.py stills <代号> 1.5,4`）
   - 透明层：`?hole=1` 把素材窗挖空，渲染成透明 VP9 webm（64–79 号：`render.py hole <代号> out.webm`）
2. **推透明层**：webm 推到 GitHub（video-drop 或本仓库），用**提交 SHA** 的 raw 链接（不要用分支名，缓存会拿到旧文件）。
3. **叠实拍素材**：剪辑服务器（MCP 工具 render）里，实拍素材作为 `layer:"base"` 铺在下面，模板透明层作为 `layer:"front"` 盖在上面。64–79 号可以用 `templates/creator-pack/compose.py` 根据 `render.py meta` 输出的素材窗位置自动生成 spec。
4. **加声音**：mux 加配音和背景音乐，画面不重新编码。
5. **检查**：get_frames 抽几帧看，确认没有字被挡住、素材窗里是对的画面，再交付。

需要的环境：Python + Playwright（Chromium）、带 libvpx-vp9 的 ffmpeg、Noto Sans/Serif CJK 字体；64–79 号要用的英文和手写字体已经放在 `templates/creator-pack/fonts/`。

## 3. Tony 定的规矩（必须遵守）

**画面**
- **抖音遮挡安全区**：竖版 1080×1920 里，顶部 0–200、**底部 1460 以下**（账号名、文案、评论框）、**右侧 930 以右、高度 860–1600**（头像/点赞/评论/分享按钮）会被抖音界面盖住。字幕、重点字、人脸都不能放进这些区域。64–79 号可以用 `render.py guide <代号> 3,5` 叠一层遮挡区检查。
- 4:3 横版（79 号）在抖音里居中显示，界面落在上下黑边，适合长口播。
- 宣传片优先做竖版（发抖音）。
- 每条视频都要用**免费实拍素材**（Mixkit 只用写了 Mixkit Stock Video Free License 的；Pexels / Pixabay 也行），而且要和模板融为一体：素材在模板下面透出来，不能生硬地贴上去。
- 需要生成图片（漫画场景、贴纸、产品图等）时交给服务器上的 Codex 按 Etsy-Tony Skills 生成，不要自己画、也不要随便搜图。

**配音**
- **不要用 Lan 女声**（2026-11-06 起禁用）。2026-11-13 起 Tony 觉得 Bo 男声不自然，在换更好的音色；网站宣传「图片去属性」那条选的是 ElevenLabs Will。用哪个音色以各方向 README 和 Tony 最新的话为准，拿不准就先问。
- AI 配音只把**配音**加速到 1.3 倍，画面、动画、音乐保持原速。
- 真人口播：先剪掉废话，整体 1.1 倍速。
- Etsy 读标准读法「艾特西 / ET-see」，不要一个字母一个字母念。
- 知识点、政策类视频，结尾引流到网站的那句不配音、不做大字，只能放小字。
- 没有 Tony 确认，不用 OpenRouter 生成视频（花钱）。

**内容**
- 政策速递、知识点、网站宣传三条线共用选题台账（video-drop `templates/policy-brief/topics.md`），同一个知识点只做一次。
- 图片去属性工具：不说我们是怎么做的，也不说卖家该不该遵守平台规则。

## 4. 加新模板

- 编号接着总表往下编（现在到 79 号，下一个是 **80 号**），加到 `templates/catalog/README.md` 的表里，写清代号、目录和要点。
- 模板目录里放 `README.md`：尺寸、参数、怎么出片、样片在哪。
- 新模板一样要守第 3 条的安全区规矩。
- 提交说明写清楚做了什么；不要提交密钥、账号、客户信息。
