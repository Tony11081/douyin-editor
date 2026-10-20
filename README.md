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
