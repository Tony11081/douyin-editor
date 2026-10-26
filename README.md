# 抖音口播剪辑服务

部署在你们自己服务器上的剪辑工具，Claude 通过「自定义连接器」调用它：
从 Google Drive 拉原片 → Whisper 中文转写 → 按逐字时间精剪（去口误、停顿、重排钩子）
→ 9:16 竖屏、推镜头、中文大字幕（重点词标黄）、顶部标题条 → 人声降噪 + 响度标准化
→ BGM 自动避让人声并淡出 → 1080p MP4 下载链接。

## 服务器要求

- Ubuntu 22.04 / 24.04 或 Debian 12，root 权限
- 至少 2 核 4GB 内存（4 核 8GB 更快）；硬盘 20GB+
- **建议用海外服务器（香港、新加坡、日本等）**：大陆服务器访问不了 Google Drive，
  而且 80/443 端口要求域名已备案
- 一个域名（如 `edit.example.com`），A 记录解析到服务器 IP，安全组放行 80、443

## 安装（一条命令）

在服务器终端（宝塔面板「终端」、云厂商网页终端或 SSH）里执行，把域名换成你自己的：

```bash
curl -fsSL https://raw.githubusercontent.com/Tony11081/douyin-editor/main/setup.sh | sudo DOMAIN=edit.你的域名.com bash
```

> 需要仓库是 Public。以后更新代码，再跑一次同样的命令即可（配置和密钥会保留）。

装完会打印一个地址，形如：

```
https://edit.你的域名.com/mcp/0f3a...（一长串密钥）
```

## 接到 Claude

claude.ai →「设置 → 连接器 → 添加自定义连接器」，名称填「抖音剪辑」，URL 填上面那个地址。
之后在对话里发 Drive 链接，说「帮我剪」就行。

## 严格执行与自检

- **严格校验**：`render` / `mux` 的方案里写错参数名（会提示「你是不是想写 captions？」）、类型不对、
  超出范围、片段超出视频时长、配音句数对不上 / 互相重叠 / 超出成片，一律直接报错，不会被忽略或偷偷改值
- **预演**：`validate_spec` 几秒内返回完整时间线、字幕、配音位置和实际生效的设置（含默认值），不渲染
- **成片自检**：每次出片自动核对分辨率、帧率、时长、每句配音位置是否有声、整体响度，结果在 `checks`；
  `mux` 还会校验画面与原片逐帧一致
- **配音核对**：`tts` 生成后用 Whisper 逐句听写并和原文比对，可能念错的句子列在 `verify.flagged`

## AI 配音（OpenRouter）

没有人声的视频（代码动画、素材混剪）可以让 Claude 直接配音：逐句生成旁白 → 按每句时长对画面
→ 渲染时铺上配音、自动出字幕、BGM 避让人声。

1. 在 [openrouter.ai](https://openrouter.ai/keys) 建一个专用 API Key，设好额度上限
2. 写进服务器配置并重启（二选一）：

   ```bash
   # 方式一：手动编辑
   nano /opt/douyin-editor/.env          # 填 OPENROUTER_API_KEY=sk-or-...
   systemctl restart douyin-editor

   # 方式二：更新代码时一起写入
   curl -fsSL https://raw.githubusercontent.com/Tony11081/douyin-editor/main/setup.sh | sudo DOMAIN=edit.你的域名.com OPENROUTER_API_KEY=sk-or-... bash
   ```

3. 默认模型是 `OPENROUTER_TTS_MODEL`（`.env` 里可改）。中文建议对比试听几个，
   例如 `bytedance-seed/seed-audio-1-0`、`fish-audio/s2.1-pro`、`openai/gpt-4o-mini-tts-2025-12-15`；
   在对话里让 Claude 调 `tts_voices` 就能看到可用模型和音色。

相关工具：`tts`（逐句配音，返回每句时长和试听链接）、`tts_voices`、`get_tts`，
`render` 的 `voiceover` 参数（把每句配音放到指定时间点）。

## AI 生成视频（OpenRouter）

和配音共用同一个 `OPENROUTER_API_KEY`。在对话里说「把这张插画做成 5 秒的动态镜头」之类即可：

- `generate_video`：文生视频，或给首帧图（`image_url`，支持 Drive 分享链接）做图生视频；
  默认竖屏 9:16、不生成环境音，生成完自动导入视频库，得到 `video_id`
- `video_models`：查可用模型，以及支持的时长、分辨率、画幅和价格
- `render` 的 `clips` 里每段可以写自己的 `video_id`，把多个生成镜头、原片拼成一条成片，
  再叠配音、字幕和 BGM

默认模型在 `.env` 的 `OPENROUTER_VIDEO_MODEL`。视频按秒计费，比配音贵得多，
建议先用短时长、低分辨率试效果，满意再出正式版。

## HeyGen 数字人口播

用你在 HeyGen 里的数字人和克隆音色，按文案生成口播视频，自动进视频库，再走正常的口播精剪流程。

1. HeyGen 后台 → Settings → API 复制 API Key
2. 写进 `.env` 的 `HEYGEN_API_KEY=` 后重启，或更新时带上：`sudo DOMAIN=... HEYGEN_API_KEY=... bash`
3. 相关工具：`heygen_avatars`（查数字人 ID）、`heygen_voices`（查音色，含克隆声音）、
   `heygen_avatar_video`（生成，`test=True` 为带水印的免费测试；`background="#00FF00"` 方便抠像）

## 网站录屏（功能演示视频）

`record_web(url, steps)` 用服务器上的 Chromium 按脚本打开网页、点击、滚动、输入，录成 1080×1920 竖屏视频
（手机布局，2 倍像素，带红色小手指、点击涟漪和黄色高亮框），自动导入视频库，并返回每一步的秒数 `marks`。

成片里有两种用法：
- `overlays: [{"video_id": 录屏, "layer": "base", "start": 口播第几秒, "from": 录屏第几秒, "duration": 秒, "fade": 0.3}]`
  ——录屏整幅盖住口播画面，口播声音和字幕照常（讲到哪个功能就切到哪个页面）。
- `clips` 里当独立片段（这段没有声音，适合配 AI 配音）。

安装脚本会执行 `playwright install --with-deps chromium`（约 150MB，浏览器装在 `/opt/douyin-editor/ms-playwright`）。

## 双语字幕

参考 BaoCut 的双语字幕做法：译文按句写，和原文对齐同一句话的时间，画面上两行显示（默认中文主字幕在上，译文小一号在下）。
- 真人口播：`clips[i].sub` 写这段的译文；一句字符串显示在整段上，列表且条数与这段中文字幕条数相同时一条对一条。
- AI 配音：`voiceover.subs` 每句配音一条译文。
- 样式：`caption_style` 的 `sub_size_ratio`、`sub_color`、`sub_outline_color`、`sub_position`（below/above）、`sub_gap`、`sub_font`。
- `validate_spec` 的结果里 `subs` 列出每条译文的时间，先预演再渲染。

## 长视频切短视频

`get_transcript(video_id, start=600, end=900, words=false)` 只读取与原片 600–900 秒相交的句子；
省略 `words` 会附逐字时间，省略全部新参数时输出格式保持不变。句子保留原编号和完整文字，
逐字列表按区间筛选，时间不从零重新计数。

`render_batch(specs=[方案一, 方案二], names=["直播切片一", "直播切片二"])` 先校验全部方案，
任一条有误就整批拒绝并指出第几条；全部通过后返回 `job_ids`，逐条 `wait_job` 获取成片。
`names` 可省略；提供时必须与方案数量相同，名称写入成片 JSON，`list_outputs` 也会返回。
批量校验不保证后续下载或编码一定成功，各任务失败仍通过 `wait_job` 报告。

超过一小时的原片每 10 分钟解码、转写一段，合并回原片时间轴，报告「已转写 X/Y 分钟」。
不会一次解码整段长视频到内存；原片仍需保留，磁盘空间和运行时间取决于视频长度。
切段交界的词可能被 ASR 截断，选剪辑点前请核对交界附近的原声。

## 专属词表

首次启动创建 `DATA_DIR/glossary.json`，已有词表保持原样。默认八条：
IC→Etsy、意见代发→一件代发、亚罗巴巴→阿里巴巴、报品→爆品、代价工→代加工、
直播客→直播课、实效→时效、上船→上传。

- `glossary_list()`：读取当前词表。
- `glossary_set(entries={"IC": "Etsy", "新错词": "正确写法"})`：追加或覆盖指定词条，其他条目保留。
- `glossary_remove(keys=["新错词"])`：删除指定词条。

转写提示会包含词表的正确写法，并保留原中文提示。渲染时，片段文字、逐字转写和配音字幕
都会应用词表；`spec.corrections` 的同名键优先，可以用 `{"IC":"IC"}` 禁用这一条自动更正。
匹配区分大小写，重叠时优先较长词，不会对替换结果再次替换；`applied.corrections` 只列实际生效的词条。
更新采用进程内锁和原子文件替换，适用于当前单服务进程的并发调用；修改不会重写已有成片。

## 首帧封面

```python
make_cover(video_id="原片编号", time=12.5, title="直播爆品\nEtsy 一件代发",
           subtitle="从选品到交付", style={"highlight": ["Etsy"], "y": 0.20})
# 也可传 output_id，和 video_id 二选一。
# wait_job 返回 cover_id、PNG download_url。
render({"video_id": "原片编号", "clips": [{"start": 10, "end": 30}],
        "cover": {"cover_id": "封面编号", "duration": 0.5}})
```

封面为 1080×1920 PNG，存于 `DATA_DIR/covers/`，下载路由 `/files/{token}/covers/{name}`。
HLG/PQ 原片复用 render 的 HDR 色调映射；默认标题位于画面上三分之一，白色 Noto Sans CJK 粗体、
黑描边，指定词标黄。标题最多两行、60 字符，过长会要求精简；`style.y` 范围 0–0.8。
安装脚本已安装 Noto CJK，也可将字体置于现有 `FONTS_DIR`。

`cover.duration` 默认 0.5 秒，必须大于零且不超过成片长度。封面按成片分辨率缩放，覆盖所有视觉层，
包括开头该时段的烧录字幕；声音连续播放，字幕与后续视频时间不位移，导出的字幕也保留原时间。
`get_frames(output_id=..., times=[0, 0.8])` 可核对封面帧及封面结束后的画面。

## 导出字幕文件

`export_subtitles(output_id="成片编号", format="srt", bilingual=true)` 返回下载链接，
格式可选 `srt` 或 `vtt`，默认单语 SRT。文件为 UTF-8，存于 `DATA_DIR/subtitles/`，
下载路由 `/files/{token}/subtitles/{name}`，与视频及封面使用相同的访问令牌。

来源是成片 JSON 的 `captions` / `subs`，不重新转写、不自动翻译。双语按原文与译文区间的交集切段：
每条第一行原文、第二行译文，长译文覆盖多个原文片段时会重复显示；一个原文片段跨越两条译文时，
在译文交界处分成两条。文本内部换行合并为空格，保证每条两行。缺失译文或译文重叠时明确报错。

对本服务成片做变速时使用 `mux({"output_id":"成片编号", "speed":1.4, "original_volume":1})`，
字幕和译文的开始、结束时间均除以 speed，再从 mux 返回的新 `output_id` 导出。
原有 `mux({"video_id":...})` 用法保留；外部导入视频没有可靠的成片字幕来源，导出时会报错，
即使导入链接曾来自本服务也不通过文件名或 URL 猜测来源。没有字幕的成片同样会明确报错。

## 离线测试

安装 Python 依赖、pytest、ffmpeg（含 libx264、libx265、zscale、libass）及 Noto CJK 后运行：

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

测试在临时目录使用 lavfi 假视频和 API / ASR 替身，不调用付费服务或下载转写模型。
原有六份脚本测试通过 pytest 在独立进程运行，以免各自的请求替身互相影响。
新测试涵盖批量拒绝、并发词表、长片时间戳、HLG 封面、首帧音画验证、双语文件解析和 mux 变速。

## 常用命令

```bash
systemctl status douyin-editor      # 运行状态
journalctl -u douyin-editor -f      # 实时日志
systemctl restart douyin-editor     # 重启
cat /opt/douyin-editor/.env         # 配置（含连接器密钥）
```

- 背景音乐：把 mp3 放进 `/opt/douyin-editor/data/music/`（注意版权，建议用抖音/剪映可商用曲库或自购曲）
- 成片在 `/opt/douyin-editor/data/outputs/`，定期清理即可
- 换密钥：改 `.env` 里的 `ACCESS_TOKEN` 后重启，再到 Claude 里更新连接器地址
