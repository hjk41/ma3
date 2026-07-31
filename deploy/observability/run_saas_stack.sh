#!/usr/bin/env bash
# Start / refresh the SaaS observability stack on the ma3.io application host.
# Requires: docker, host networking, uvicorn on the live blue-green port with
# MA3_METRICS_ENABLED=1, optional /etc/ma3/feishu.env for Alertmanager → Feishu.
#
# Does NOT remote_write to Aliyun-managed Prometheus — scrape + UI stay on this host
# (loopback :9090 / :9093 / :3000).
#
# Usage (on the app host):
#   bash deploy/observability/run_saas_stack.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OBS_DIR="${ROOT}"
PROM_CFG="${OBS_DIR}/prometheus"
AM_CFG="${OBS_DIR}/alertmanager"
GF_DIR="${OBS_DIR}/grafana"

# Prefer REMOTE_DIR from env; else find deploy root that contains ma3.env / data/.
REMOTE_DIR="${REMOTE_DIR:-}"
if [[ -z "${REMOTE_DIR}" ]]; then
  # Flat layout: <root>/deploy/observability → up 2
  # Nested layout: <root>/code/deploy/observability → up 3
  for cand in "$(cd "${OBS_DIR}/../.." && pwd)" "$(cd "${OBS_DIR}/../../.." && pwd)"; do
    if [[ -f "${cand}/ma3.env" || -d "${cand}/data" ]]; then
      REMOTE_DIR="${cand}"
      break
    fi
  done
  REMOTE_DIR="${REMOTE_DIR:-$(cd "${OBS_DIR}/../.." && pwd)}"
fi
BLUEGREEN_DIR="${REMOTE_DIR}/data/bluegreen"
TARGETS_FILE="${BLUEGREEN_DIR}/prometheus-targets.json"
PORT_A="${BLUE_GREEN_PORT_A:-8000}"
PORT_B="${BLUE_GREEN_PORT_B:-8001}"

need() { command -v "$1" >/dev/null || { echo "missing $1" >&2; exit 1; }; }
need docker
need curl

write_targets() {
  local port="$1"
  mkdir -p "${BLUEGREEN_DIR}"
  local tmp
  tmp="${TARGETS_FILE}.tmp.$$"
  cat >"${tmp}" <<EOF
[
  {
    "targets": ["127.0.0.1:${port}"],
    "labels": {
      "service": "ma3"
    }
  }
]
EOF
  mv -f "${tmp}" "${TARGETS_FILE}"
  echo "prometheus file_sd -> 127.0.0.1:${port} (${TARGETS_FILE})"
}

ensure_targets() {
  if [[ -f "${TARGETS_FILE}" ]]; then
    echo "using existing ${TARGETS_FILE}"
    cat "${TARGETS_FILE}"
    return 0
  fi
  local port=""
  if curl -sf "http://127.0.0.1:${PORT_B}/healthz" >/dev/null 2>&1; then
    port="${PORT_B}"
  elif curl -sf "http://127.0.0.1:${PORT_A}/healthz" >/dev/null 2>&1; then
    port="${PORT_A}"
  else
    port="${PORT_A}"
    echo "WARN: neither :${PORT_A} nor :${PORT_B} answered /healthz; defaulting scrape to :${port}" >&2
  fi
  # Prefer recorded active_port when present.
  if [[ -f "${BLUEGREEN_DIR}/active_port" ]]; then
    local recorded
    recorded="$(tr -d '[:space:]' <"${BLUEGREEN_DIR}/active_port" || true)"
    if [[ "${recorded}" == "${PORT_A}" || "${recorded}" == "${PORT_B}" ]]; then
      if curl -sf "http://127.0.0.1:${recorded}/healthz" >/dev/null 2>&1; then
        port="${recorded}"
      fi
    fi
  fi
  write_targets "${port}"
}

ensure_targets

echo "==> alert sink (Feishu forwarder) on 127.0.0.1:8787"
mkdir -p /var/log/ma3 /usr/local/lib/ma3
cp -f "${OBS_DIR}/local_webhook_sink.py" /usr/local/lib/ma3/local_webhook_sink.py
if [[ -f /etc/systemd/system/ma3-alert-sink.service ]]; then
  systemctl daemon-reload
  systemctl enable --now ma3-alert-sink.service
  systemctl restart ma3-alert-sink.service
else
  # One-shot nohup fallback when systemd unit is not installed yet.
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

echo "==> prometheus (host network, :9090 loopback; blue-green file_sd)"
docker rm -f ma3-prometheus 2>/dev/null || true
docker volume create ma3_prom_data >/dev/null
docker run -d --name ma3-prometheus --restart unless-stopped \
  --network host \
  -v "${PROM_CFG}/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "${PROM_CFG}/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  -v "${PROM_CFG}/slo-rules.yml:/etc/prometheus/slo-rules.yml:ro" \
  -v "${BLUEGREEN_DIR}:/etc/prometheus/file_sd:ro" \
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
curl -sf 'http://127.0.0.1:9090/api/v1/rules' | python3 -c 'import sys,json;d=json.load(sys.stdin);gs=d.get("data",{}).get("groups",[]);print("rule_groups",len(gs),[g.get("name") for g in gs])'
curl -sf 'http://127.0.0.1:9090/api/v1/targets' | python3 -c '
import sys, json
d = json.load(sys.stdin)
for t in d.get("data", {}).get("activeTargets", []):
    print("target", t.get("labels", {}).get("job"), t.get("scrapeUrl"), t.get("health"))
'
echo "OK: prometheus :9090  alertmanager :9093  grafana :3000 (all loopback; no Aliyun remote_write)"
