# 春招平行宇宙 · 部署快捷命令
# 用法: make <target>

.PHONY: deploy build package clean help

help:
	@echo "春招平行宇宙 · 部署命令"
	@echo ""
	@echo "  make build         本地构建前端 + 检查后端"
	@echo "  make package       打包构建产物 + 部署脚本 → dist/deploy-package.tar.gz"
	@echo "  make deploy-local  在本机部署（开发测试用）"
	@echo "  make clean         清理构建产物"

build:
	@echo "=== 构建前端 ==="
	cd frontend && npm ci --silent && npm run build
	@echo "=== 检查后端 ==="
	cd backend && python3 -c "import app; print('backend OK')"

package:
	@echo "=== 打包部署包 ==="
	@mkdir -p dist
	@tar czf dist/deploy-package.tar.gz \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='.venv' \
		--exclude='venv' \
		--exclude='backend/data/users' \
		--exclude='backend/data/video' \
		--exclude='.env' \
		--exclude='node_modules' \
		deploy/ \
		backend/ \
		frontend/dist/
	@ls -lh dist/deploy-package.tar.gz
	@echo ""
	@echo "  部署: scp dist/deploy-package.tar.gz user@host:/opt/"
	@echo "        ssh user@host 'cd /opt && tar xzf deploy-package.tar.gz && cd deploy && bash deploy.sh --local --domain 你的域名'"

deploy-local:
	bash deploy/deploy.sh --local --domain $${DOMAIN:-localhost}

deploy-remote:
	@if [ -z "$(HOST)" ]; then echo "用法: make deploy-remote HOST=<IP> DOMAIN=<domain>"; exit 1; fi
	bash deploy/deploy.sh --host $(HOST) --domain $${DOMAIN:-multiverse.zdwktlj.top} --ssh-key $${SSH_KEY:-~/.ssh/id_ed25519}

clean:
	rm -rf frontend/dist
	rm -rf dist/deploy-package.tar.gz
	@echo "清理完成"
