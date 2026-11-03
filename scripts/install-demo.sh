#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pivot_port="${PIVOT_PORT:-8080}"
pivot_bind="${PIVOT_BIND:-127.0.0.1}"
pivot_name=pivot-demo
if [[ ! "$pivot_port" =~ ^[0-9]+$ ]] || (( 10#$pivot_port < 1024 || 10#$pivot_port > 65535 )); then printf 'Invalid PIVOT_PORT (1024–65535).\n' >&2; exit 1; fi
if [[ "$pivot_bind" != 127.0.0.1 && "$pivot_bind" != 0.0.0.0 ]]; then printf 'PIVOT_BIND must be 127.0.0.1 or 0.0.0.0.\n' >&2; exit 1; fi
command -v docker >/dev/null || { printf 'Docker Engine is required. No software was installed.\n' >&2; exit 1; }
pivot_platform="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
if [[ "$pivot_platform" != linux/amd64 ]]; then printf 'This package requires linux/amd64 Docker; found %s. Use the architecture-independent static archive instead.\n' "$pivot_platform" >&2; exit 1; fi
sha256sum --check SHA256SUMS
if docker container inspect "$pivot_name" --format '{{.Id}}' >/dev/null 2>&1; then
  printf 'Container pivot-demo already exists; left unchanged. Inspect it before stopping or replacing it.\n' >&2; exit 1
fi
docker load -i pivot-demo-image-linux-amd64.tar.gz
if [[ "$(docker image inspect pivot-demo:linux-amd64 --format '{{.Os}}/{{.Architecture}}')" != linux/amd64 ]]; then printf 'Loaded image platform mismatch.\n' >&2; exit 1; fi
docker run -d --name "$pivot_name" --label org.pivot.surface=demo-release \
  --restart unless-stopped --memory=128m --cpus=0.5 --read-only \
  --tmpfs /var/cache/nginx --tmpfs /var/run --tmpfs /tmp \
  -p "${pivot_bind}:${pivot_port}:80" pivot-demo:linux-amd64 >/dev/null
pivot_ready=false
for pivot_attempt in {1..40}; do
  if docker exec "$pivot_name" wget -q -O - http://127.0.0.1/health >/dev/null 2>&1; then pivot_ready=true; break; fi
  sleep 0.25
done
if [[ "$pivot_ready" != true ]]; then printf 'Health check failed. Inspect: docker logs pivot-demo\n' >&2; exit 1; fi
printf 'Pivot is ready on %s:%s. Synthetic local-browser demo; no API keys, database or email.\n' "$pivot_bind" "$pivot_port"
