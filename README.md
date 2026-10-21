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
