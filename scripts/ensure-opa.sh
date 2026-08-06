#!/usr/bin/env bash
# Ensures an `opa` binary is available at .bin/opa, downloading the pinned
# version if neither a system opa nor a cached one already satisfies it.
set -euo pipefail
cd "$(dirname "$0")/.."

OPA_VERSION="v1.19.0"

if command -v opa >/dev/null 2>&1; then
  echo "$(command -v opa)"
  exit 0
fi

if [ -x .bin/opa ]; then
  echo ".bin/opa"
  exit 0
fi

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$arch" in
  x86_64) arch="amd64" ;;
  aarch64|arm64) arch="arm64" ;;
  *) echo "unsupported arch: $arch" >&2; exit 1 ;;
esac

mkdir -p .bin
url="https://openpolicyagent.org/downloads/${OPA_VERSION}/opa_${os}_${arch}_static"
curl -sL -o .bin/opa "$url"
chmod +x .bin/opa
echo ".bin/opa"
