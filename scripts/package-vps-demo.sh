#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for pivot_input in artifacts/pivot-demo-image-linux-amd64.tar.gz artifacts/pivot-demo-static.tar.gz; do
  [[ -f "$pivot_input" ]] || { printf 'Run ./scripts/build-demo.sh --image first.\n' >&2; exit 1; }
done
pivot_stage="$(mktemp -d artifacts/pivot-package.XXXXXX)"
trap 'rm -rf "$pivot_stage"' EXIT
mkdir -p "$pivot_stage/pivot-demo-linux-amd64"
cp artifacts/pivot-demo-image-linux-amd64.tar.gz artifacts/pivot-demo-static.tar.gz "$pivot_stage/pivot-demo-linux-amd64/"
cp scripts/install-demo.sh "$pivot_stage/pivot-demo-linux-amd64/install.sh"
cp infrastructure/demo/INSTALL.md "$pivot_stage/pivot-demo-linux-amd64/README.md"
(
  cd "$pivot_stage/pivot-demo-linux-amd64"
  if command -v sha256sum >/dev/null; then sha256sum install.sh README.md pivot-demo-image-linux-amd64.tar.gz pivot-demo-static.tar.gz > SHA256SUMS
  else shasum -a 256 install.sh README.md pivot-demo-image-linux-amd64.tar.gz pivot-demo-static.tar.gz > SHA256SUMS; fi
)
tar -C "$pivot_stage" -czf artifacts/pivot-vps-linux-amd64.tar.gz pivot-demo-linux-amd64
(
  cd artifacts
  if command -v sha256sum >/dev/null; then sha256sum pivot-vps-linux-amd64.tar.gz pivot-demo-image-linux-amd64.tar.gz pivot-demo-static.tar.gz > pivot-demo-SHA256SUMS
  else shasum -a 256 pivot-vps-linux-amd64.tar.gz pivot-demo-image-linux-amd64.tar.gz pivot-demo-static.tar.gz > pivot-demo-SHA256SUMS; fi
)
printf 'VPS package: artifacts/pivot-vps-linux-amd64.tar.gz\nChecksums: artifacts/pivot-demo-SHA256SUMS\n'
