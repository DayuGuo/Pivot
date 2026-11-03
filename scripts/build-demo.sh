#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" != "" && "${1:-}" != --image ]]; then printf 'Usage: ./scripts/build-demo.sh [--image]\n' >&2; exit 1; fi
mkdir -p artifacts
demo_platform="${DEMO_PLATFORM:-$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')}"
demo_tag=publishing-os-demo:local
if [[ "${1:-}" == --image ]]; then
  demo_platform="${DEMO_PLATFORM:-linux/amd64}"
  demo_tag="publishing-os-demo:${demo_platform//\//-}"
fi
if [[ "$demo_platform" != linux/amd64 && "$demo_platform" != linux/arm64 ]]; then printf 'Supported DEMO_PLATFORM: linux/amd64 or linux/arm64.\n' >&2; exit 1; fi
docker build --platform "$demo_platform" -f infrastructure/demo/Dockerfile -t "$demo_tag" .
demo_export_container="$(docker create --platform "$demo_platform" "$demo_tag")"
demo_export_dir="$(mktemp -d artifacts/demo-export.XXXXXX)"
trap 'docker rm "$demo_export_container" >/dev/null; rm -rf "$demo_export_dir"' EXIT
docker cp "$demo_export_container:/usr/share/nginx/html/." "$demo_export_dir/"
cp infrastructure/demo/nginx.conf "$demo_export_dir/nginx.conf.example"
tar -C "$demo_export_dir" -czf artifacts/publishing-os-demo-static.tar.gz .
if [[ "${1:-}" == --image ]]; then
  demo_image_archive="artifacts/publishing-os-demo-image-${demo_platform//\//-}.tar.gz"
  docker save "$demo_tag" | gzip -n > "$demo_image_archive"
  printf 'Offline image (%s): %s\n' "$demo_platform" "$demo_image_archive"
fi
printf 'Static package: artifacts/publishing-os-demo-static.tar.gz\nImage: %s (%s)\n' "$demo_tag" "$demo_platform"
