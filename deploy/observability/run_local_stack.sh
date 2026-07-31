#!/usr/bin/env bash
# Optional LOCAL observability stack (operator laptop / LAN host — NOT ma3.io).
#
# Production app-host stack: bash deploy/observability/run_saas_stack.sh on ma3.io.
# This script is a laptop lab only.
#
# Usage (local):
#   bash deploy/observability/run_local_stack.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OBS_DIR="${ROOT}"
PROM_CFG="${OBS_DIR}/prometheus"
AM_CFG="${OBS_DIR}/alertmanager"
GF_DIR="${OBS_DIR}/grafana"

need() { command -v "$1" >/dev/null || { echo "missing $1" >&2; exit 1; }; }
need docker
need curl

# Refuse on the production app checkout (Aliyun host layout).
if [[ -f /opt/ma3_deploy/ma3.env ]] && ss -ltn 2>/dev/null | grep -qE '127\.0\.0\.1:800[01]\b'; then
  echo "REFUSING: looks like the ma3.io app host. Use: bash deploy/observability/run_saas_stack.sh" >&2
  exit 2
fi

echo "==> alert sink (Feishu forwarder) on 127.0.0.1:8787"
mkdir -p /var/log/ma3 /usr/local/lib/ma3
cp -f "${OBS_DIR}/local_webhook_sink.py" /usr/local/lib/ma3/local_webhook_sink.py
if [[ -f /etc/systemd/system/ma3-alert-sink.service ]]; then
  systemctl daemon-reload
  systemctl enable --now ma3-alert-sink.service
  systemctl restart ma3-alert-sink.service
else
  pkill -f local_webhook_sink.py || true
  set -a
  # shellcheck disable=SC1091
  [[ -f /etc/ma3/feishu.env ]] && source /etc/ma3/feishu.env
  set +a
  nohup /usr/bin/python3 /usr/local/lib/ma3/local_webhook_sink.py \
    >/var/log/ma3/alert-sink.out 2>&1 &
  echo $! >/var/run/ma3-alert-sink.pid
fi
sleep 1
curl -sf http://127.0.0.1:8787/ >/dev/null

echo "==> prometheus (host network, :9090 loopback) — local/lab only"
docker rm -f ma3-prometheus 2>/dev/null || true
docker volume create ma3_prom_data >/dev/null
docker run -d --name ma3-prometheus --restart unless-stopped \
  --network host \
  -v "${PROM_CFG}/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "${PROM_CFG}/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  -v "${PROM_CFG}/slo-rules.yml:/etc/prometheus/slo-rules.yml:ro" \
  -v ma3_prom_data:/prometheus \
  prom/prometheus:v2.54.1 \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=30d \
  --web.enable-lifecycle \
  --web.listen-address=127.0.0.1:9090

echo "==> alertmanager (host network, :9093 loopback)"
docker rm -f ma3-alertmanager 2>/dev/null || true
docker run -d --name ma3-alertmanager --restart unless-stopped \
  --network host \
  -v "${AM_CFG}/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
  prom/alertmanager:v0.27.0 \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.listen-address=127.0.0.1:9093

echo "==> grafana (host network, :3000 loopback)"
docker rm -f ma3-grafana 2>/dev/null || true
docker volume create ma3_grafana_data >/dev/null
docker run -d --name ma3-grafana --restart unless-stopped \
  --network host \
  -e GF_SERVER_HTTP_ADDR=127.0.0.1 \
  -e GF_SERVER_HTTP_PORT=3000 \
  -e GF_SECURITY_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}" \
  -e GF_SECURITY_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-ma3-change-me}" \
  -e GF_USERS_ALLOW_SIGN_UP=false \
  -e GF_AUTH_ANONYMOUS_ENABLED=false \
  -v ma3_grafana_data:/var/lib/grafana \
  -v "${GF_DIR}/provisioning:/etc/grafana/provisioning:ro" \
  -v "${GF_DIR}/ma3-slo.json:/var/lib/grafana/dashboards/ma3-slo.json:ro" \
  grafana/grafana:11.2.0

sleep 5
echo "==> readiness"
curl -sf http://127.0.0.1:9090/-/ready
echo
curl -sf http://127.0.0.1:9093/-/ready
echo
curl -sf -o /dev/null -w "grafana %{http_code}\n" http://127.0.0.1:3000/login || true
echo "OK: local prometheus :9090  alertmanager :9093  grafana :3000"
echo "NOTE: SaaS uptime alerts = ma3-probe.timer → Feishu (not this stack)."
