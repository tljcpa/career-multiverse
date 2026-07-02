#!/usr/bin/env bash
# ===== 春招平行宇宙 · 可复用部署脚本 (Caddy 版) =====
# 适用: Ubuntu 22.04（任何云/物理机，不绑定厂商）
# Web server: Caddy（比 nginx 更简单，自动 SSL，配置短）
# 负载均衡: 在 Caddyfile 的 reverse_proxy 后加多个 upstream 即可
#
# 用法:
#   远程部署: ./deploy.sh --host 1.2.3.4 --domain multiverse.zdwktlj.top
#   本地部署: ./deploy.sh --local --domain multiverse.zdwktlj.top
#   仅构建:   ./deploy.sh --build-only
# 幂等: 可反复执行

set -euo pipefail

# ===== 参数解析 =====
HOST=""
SSH_KEY="$HOME/.ssh/id_ed25519"
DOMAIN=""
LOCAL=false
BUILD_ONLY=false
BRANCH="main"
REPO_URL="https://github.com/tljcpa/career-multiverse.git"
REMOTE_APP_DIR="/opt/career-multiverse"
WEBROOT="/var/www/multiverse"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --local) LOCAL=true; shift ;;
    --build-only) BUILD_ONLY=true; shift ;;
    --branch) BRANCH="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

if [ "$BUILD_ONLY" = false ] && [ "$LOCAL" = false ] && [ -z "$HOST" ]; then
  echo "用法: $0 --host <IP> [--domain <domain>]"
  echo "  或  $0 --local [--domain <domain>]"
  echo "  或  $0 --build-only"
  exit 1
fi

# ===== 路径推导 =====
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ "$LOCAL" = true ] || [ "$BUILD_ONLY" = true ]; then
  APP_DIR="$LOCAL_PROJECT_ROOT"
else
  APP_DIR="$REMOTE_APP_DIR"
fi

BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"

# SSH
SSH_CMD="bash -c"
if [ "$LOCAL" = false ] && [ -n "$HOST" ]; then
  SSH_BASE="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
  SSH_CMD="$SSH_BASE -i $SSH_KEY azureuser@$HOST"
fi

# ===== 工具函数 =====
remote() {
  echo "  [REMOTE] $1"
  if [ "$LOCAL" = true ]; then
    bash -c "$1"
  else
    $SSH_CMD "$1"
  fi
}

upload() {
  local src="$1" dst="$2"
  if [ "$LOCAL" = true ]; then
    cp "$src" "$dst"
  else
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$src" "azureuser@$HOST:$dst"
  fi
}

step_header() { echo; echo "===== [$1] $2 ====="; }

# ===== 1. 系统依赖 =====
step_header "1/5" "安装系统依赖"
remote "
  set -e
  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get update -qq

  # Python
  command -v python3 >/dev/null || sudo apt-get install -y -qq python3 python3-pip python3-venv
  # python3-venv (Ubuntu 22.04 可能缺)
  dpkg -l python3.10-venv >/dev/null 2>&1 || sudo apt-get install -y -qq python3.10-venv

  # Caddy
  if ! command -v caddy >/dev/null 2>&1; then
    sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo 'deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update -qq
    sudo apt-get install -y -qq caddy
  fi

  # Node.js 18
  if ! command -v node >/dev/null 2>&1 || [ \$(node -v | cut -d. -f1 | tr -d v) -lt 18 ]; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - > /dev/null 2>&1
    sudo apt-get install -y -qq nodejs
  fi

  # git
  command -v git >/dev/null 2>&1 || sudo apt-get install -y -qq git
  echo '  系统依赖就绪'
"

# ===== 2. 代码部署 =====
step_header "2/5" "部署代码"
if [ "$LOCAL" = true ]; then
  echo "  使用本地代码: $APP_DIR"
else
  # 上传部署包
  if [ -f "$LOCAL_PROJECT_ROOT/dist/deploy-package.tar.gz" ]; then
    upload "$LOCAL_PROJECT_ROOT/dist/deploy-package.tar.gz" "/tmp/deploy-package.tar.gz"
  fi
  remote "
    set -e
    if [ -f /tmp/deploy-package.tar.gz ]; then
      sudo rm -rf '$APP_DIR'
      sudo mkdir -p '$APP_DIR'
      sudo chown azureuser:azureuser '$APP_DIR'
      cd '$APP_DIR' && tar xzf /tmp/deploy-package.tar.gz
      echo '  代码(包)就绪'
    elif [ -d '$APP_DIR/.git' ]; then
      cd '$APP_DIR' && git fetch origin && git reset --hard origin/$BRANCH
      echo '  代码(git)更新'
    else
      sudo mkdir -p '$APP_DIR'
      sudo chown azureuser:azureuser '$APP_DIR'
      git clone --branch $BRANCH '$REPO_URL' '$APP_DIR'
      echo '  代码(git)克隆'
    fi
  "
fi

# 上传 .env (如果有)
if [ "$LOCAL" = false ] && [ -f "$LOCAL_PROJECT_ROOT/.env" ]; then
  upload "$LOCAL_PROJECT_ROOT/.env" "$BACKEND_DIR/.env"
fi

# ===== 3. 后端 =====
step_header "3/5" "配置后端"
remote "
  set -e
  cd '$BACKEND_DIR'

  # venv
  python3 -m venv venv 2>/dev/null || true
  ./venv/bin/pip install -q pip --upgrade 2>/dev/null
  ./venv/bin/pip install -q -r requirements.txt 2>&1 | tail -1

  # ensure production mode
  grep -q 'APP_ENV=' .env 2>/dev/null && sed -i 's/APP_ENV=.*/APP_ENV=production/' .env || echo 'APP_ENV=production' >> .env
"

# systemd
remote "
  sudo tee /etc/systemd/system/multiverse-backend.service > /dev/null <<'UNIT'
[Unit]
Description=Career Multiverse Backend
After=network.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3
EnvironmentFile=$BACKEND_DIR/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable multiverse-backend --now
  sudo systemctl restart multiverse-backend
  sleep 2
  curl -sf http://127.0.0.1:8000/ > /dev/null && echo '  Backend OK' || echo '  [WARN] Backend check failed'
"

# ===== 4. 前端 =====
step_header "4/5" "部署前端"
if [ "$LOCAL" = true ]; then
  if [ ! -d "$FRONTEND_DIR/dist" ]; then
    cd "$FRONTEND_DIR" && npm ci --silent && npm run build
  fi
  remote "sudo mkdir -p '$WEBROOT' && sudo cp -r '$FRONTEND_DIR/dist/'* '$WEBROOT/' && sudo chown -R azureuser:azureuser '$WEBROOT'"
else
  # 本机已有构建产物
  if [ -d "$LOCAL_PROJECT_ROOT/frontend/dist" ]; then
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -r "$LOCAL_PROJECT_ROOT/frontend/dist" "azureuser@$HOST:/tmp/frontend-dist" 2>/dev/null
    remote "sudo mkdir -p '$WEBROOT' && sudo cp -r /tmp/frontend-dist/* '$WEBROOT/' && sudo chown -R azureuser:azureuser '$WEBROOT'"
  fi
fi
echo "  前端 → $WEBROOT"

# ===== 5. Caddy =====
step_header "5/5" "配置 Caddy"
SERVER_NAME="${DOMAIN:-_}"

if [ -n "$DOMAIN" ]; then
  # 有域名：自动 SSL
  CADDY_SITE="
# 春招平行宇宙
$DOMAIN {
	reverse_proxy /api/* localhost:8000
	@spaFallback {
		not file
		not path /api/*
	}
	rewrite @spaFallback /index.html
	root * $WEBROOT
	encode gzip
	file_server
}"
else
  # 无域名：HTTP only
  CADDY_SITE="
# 春招平行宇宙（IP 直连）
:80 {
	reverse_proxy /api/* localhost:8000
	@spaFallback {
		not file
		not path /api/*
	}
	rewrite @spaFallback /index.html
	root * $WEBROOT
	encode gzip
	file_server
}"
fi

remote "
  # 不覆盖已有 Caddyfile，追加（幂等）
  if ! sudo grep -q '春招平行宇宙' /etc/caddy/Caddyfile 2>/dev/null; then
    echo '$CADDY_SITE' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
  else
    echo '  Caddy 站点已存在，跳过'
  fi
  sudo caddy validate --config /etc/caddy/Caddyfile 2>/dev/null && sudo systemctl reload caddy 2>/dev/null || echo '  [WARN] Caddy reload failed, check config'
  echo '  Caddy 配置完成'
"

# ===== 完成 =====
echo
echo "============================================"
if [ "$LOCAL" = true ]; then
  echo "  部署完成! http://localhost"
else
  echo "  部署完成! http://$HOST"
fi
if [ -n "$DOMAIN" ]; then
  echo "  域名: https://$DOMAIN (Caddy 自动 SSL)"
fi
echo "  日志: sudo journalctl -u multiverse-backend -f"
echo "============================================"
