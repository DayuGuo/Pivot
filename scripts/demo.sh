#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
demo_name=publishing-os-static-demo
demo_port="${DEMO_PORT:-3110}"
demo_action="${1:-start}"
if [[ ! "$demo_port" =~ ^[0-9]+$ ]] || (( 10#$demo_port < 1024 || 10#$demo_port > 65535 )); then
  printf 'DEMO_PORT must be between 1024 and 65535.\n' >&2; exit 1
fi
if [[ "$demo_action" != start && "$demo_action" != stop ]]; then
  printf 'Usage: ./scripts/demo.sh [start|stop]\n' >&2; exit 1
fi
if docker container inspect "$demo_name" --format '{{.Id}}' >/dev/null 2>&1; then
  demo_label="$(docker container inspect "$demo_name" --format '{{index .Config.Labels "org.publishing-os.surface"}}')"
  if [[ "$demo_label" != static-demo ]]; then
    printf 'Container name is already in use by an unmanaged container; no changes made.\n' >&2; exit 1
  fi
fi
if [[ "$demo_action" == stop ]]; then
  if docker container inspect "$demo_name" --format '{{.Id}}' >/dev/null 2>&1; then docker rm -f "$demo_name" >/dev/null; fi
  printf 'Local static demo stopped.\n'; exit 0
fi
bash scripts/build-demo.sh
if docker container inspect "$demo_name" --format '{{.Id}}' >/dev/null 2>&1; then docker rm -f "$demo_name" >/dev/null; fi
docker run -d --name "$demo_name" --label org.publishing-os.surface=static-demo \
  --restart unless-stopped --memory=128m --cpus=0.5 --read-only \
  --tmpfs /var/cache/nginx --tmpfs /var/run --tmpfs /tmp \
  -p "127.0.0.1:${demo_port}:80" pivot-demo:local >/dev/null
demo_ready=false
for demo_attempt in {1..40}; do
  if docker exec "$demo_name" wget -q -O - http://127.0.0.1/health >/dev/null 2>&1; then demo_ready=true; break; fi
  sleep 0.25
done
if [[ "$demo_ready" != true ]]; then printf 'Demo failed its startup health check; inspect the dedicated container logs.\n' >&2; exit 1; fi
printf 'Demo: http://localhost:%s\nNo API, model credentials or database required.\n' "$demo_port"
