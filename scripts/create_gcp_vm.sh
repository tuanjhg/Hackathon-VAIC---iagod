#!/usr/bin/env bash
# Backward-compatible entry point. The implementation lives in scripts/gcp.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/gcp/01-provision.sh" "$@"
