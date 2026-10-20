#!/usr/bin/env bash
# 抖音口播剪辑服务 一键安装（Ubuntu 22.04+/Debian 12+，需 root）
# 用法：  sudo bash install.sh                 # 只用 IP + 端口（HTTP，仅测试）
#        sudo DOMAIN=edit.你的域名.com bash install.sh   # 自动申请 HTTPS（推荐，Claude 连接器需要 HTTPS）
set -euo pipefail

APP_DIR=/opt/douyin-editor
PORT=${PORT:-8000}
DOMAIN=${DOMAIN:-}
SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

say() { echo -e "\n\033[1;32m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m[注意] $*\033[0m"; }

[ "$(id -u)" = 0 ] || { echo "请用 root 运行：sudo bash install.sh"; exit 1; }
[ -f "$SRC_DIR/app/server.py" ] || { echo "找不到 app/server.py，请在解压后的目录里运行"; exit 1; }

say "检查网络环境"
CN=0
if ! curl -s --max-time 6 -o /dev/null https://www.google.com; then
  CN=1
  warn "这台服务器访问不了 Google（可能在中国大陆）。"
  warn "这样服务器无法从 Google Drive 下载视频，只能用国内可访问的视频直链。建议换香港/新加坡等海外服务器。"
fi

say "安装系统依赖（ffmpeg、中文字体、Python）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ffmpeg fonts-noto-cjk python3 python3-venv python3-pip curl ca-certificates
apt-get install -y fonts-noto-cjk-extra || warn "没装上 fonts-noto-cjk-extra，字幕会用 Bold 粗体代替 Black 特粗"

say "复制程序到 $APP_DIR"
mkdir -p "$APP_DIR/data/music"
cp -r "$SRC_DIR/app" "$SRC_DIR/requirements.txt" "$APP_DIR/"

say "安装 Python 依赖（首次较慢）"
python3 -m venv "$APP_DIR/venv"
PIP_ARGS=()
[ $CN = 1 ] && PIP_ARGS=(-i https://pypi.tuna.tsinghua.edu.cn/simple)
"$APP_DIR/venv/bin/pip" install -q --upgrade pip "${PIP_ARGS[@]}"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" "${PIP_ARGS[@]}"

# 字体：有 Black 特粗用特粗，否则用粗体
FONT="Noto Sans CJK SC Black"
fc-list | grep -q "Noto Sans CJK SC Black" || FONT="Noto Sans CJK SC Bold"

# 内存小于 6GB 用 small 模型，否则用 medium（中文更准）
MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
MODEL=medium; [ "$MEM_GB" -lt 6 ] && MODEL=small

if [ -f "$APP_DIR/.env" ]; then
  say "保留已有配置 $APP_DIR/.env"
else
  TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  if [ -n "$DOMAIN" ]; then PUBLIC_URL="https://$DOMAIN"; else
    IP=$(curl -s --max-time 6 https://api.ipify.org || hostname -I | awk '{print $1}')
    PUBLIC_URL="http://$IP:$PORT"
  fi
  cat > "$APP_DIR/.env" <<EOF
ACCESS_TOKEN=$TOKEN
PUBLIC_URL=$PUBLIC_URL
PORT=$PORT
DATA_DIR=$APP_DIR/data
WHISPER_MODEL=$MODEL
CAPTION_FONT=$FONT
RENDER_WORKERS=1
EOF
  [ $CN = 1 ] && echo "HF_ENDPOINT=https://hf-mirror.com" >> "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

say "注册系统服务（开机自启）"
cat > /etc/systemd/system/douyin-editor.service <<EOF
[Unit]
Description=Douyin talking-head editor MCP server
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR/app
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now douyin-editor
systemctl restart douyin-editor

if [ -n "$DOMAIN" ]; then
  say "配置 HTTPS（Caddy 自动申请证书）"
  if ! command -v caddy >/dev/null; then
    apt-get install -y caddy || {
      apt-get install -y debian-keyring debian-archive-keyring apt-transport-https gnupg
      curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
      apt-get update -y && apt-get install -y caddy; }
  fi
  cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    request_body {
        max_size 20MB
    }
    reverse_proxy 127.0.0.1:$PORT {
        transport http {
            read_timeout 10m
            write_timeout 10m
        }
    }
}
EOF
  systemctl enable caddy && systemctl restart caddy
  warn "请确认域名 $DOMAIN 已解析到这台服务器，且防火墙/安全组放行了 80 和 443 端口。"
else
  warn "没有设置 DOMAIN，现在是 HTTP。Claude 连接器要求 HTTPS，正式使用请带上域名重新运行："
  warn "  sudo DOMAIN=edit.你的域名.com bash install.sh"
  warn "并在安全组放行端口 $PORT（测试用）。"
fi

say "预下载语音识别模型（$MODEL，几分钟）"
( cd "$APP_DIR/app" && set -a && . "$APP_DIR/.env" && set +a && \
  "$APP_DIR/venv/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('$MODEL', device='auto', compute_type='int8')" ) \
  || warn "模型预下载失败，第一次转写时会自动再下载"

sleep 2
. "$APP_DIR/.env"
if curl -s --max-time 5 "http://127.0.0.1:$PORT/health" | grep -q ok; then
  say "安装完成！"
  echo
  echo "  把下面这个地址填到 Claude「设置 → 连接器 → 添加自定义连接器」："
  echo
  echo -e "  \033[1;36m$PUBLIC_URL/mcp/$ACCESS_TOKEN\033[0m"
  echo
  echo "  这个地址等于密码，不要发给别人。查看日志：journalctl -u douyin-editor -f"
else
  warn "服务没起来，查看原因：journalctl -u douyin-editor -n 50"
  exit 1
fi
