# 春招平行宇宙 · 部署指南

## 架构

```
浏览器 → Caddy (:80/:443)
         ├─ /api/*  → 127.0.0.1:8000 (uvicorn, 2 workers)
         └─ /       → /var/www/multiverse/ (Vue 3 SPA)
```

Caddy 自动 SSL（Let's Encrypt），无需 certbot。

## 快速部署

```bash
# 远程一键部署
bash deploy/deploy.sh --host 40.123.241.129 --domain multiverse.zdwktlj.top

# 本地部署
bash deploy/deploy.sh --local --domain multiverse.zdwktlj.top
```

## 负载均衡

Caddy 原生支持多 upstream：

```caddy
reverse_proxy /api/* backend1:8000 backend2:8000 backend3:8000
```

加节点时改 Caddyfile 的 reverse_proxy 行即可，systemctl reload caddy 生效，无需额外配置。

## 故障排查

```bash
sudo systemctl status multiverse-backend
sudo journalctl -u multiverse-backend -f
sudo journalctl -u caddy -f
sudo caddy validate --config /etc/caddy/Caddyfile
```
