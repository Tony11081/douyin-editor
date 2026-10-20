#!/usr/bin/env bash
# 从 GitHub 下载最新代码并安装。用法（在服务器上）：
#   curl -fsSL https://raw.githubusercontent.com/Tony11081/douyin-editor/main/setup.sh | sudo DOMAIN=edit.你的域名.com bash
set -euo pipefail
REPO=${REPO:-Tony11081/douyin-editor}
BRANCH=${BRANCH:-main}
TMP=$(mktemp -d)
echo "==> 下载 $REPO ($BRANCH)"
curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz -C "$TMP"
bash "$TMP"/*/install.sh
