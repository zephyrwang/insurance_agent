#!/usr/bin/env bash
# Development quality check script
# Usage:
#   ./scripts/quality_check.sh          — check + format
#   ./scripts/quality_check.sh --check  — check only (no writes, exits non-zero if unformatted)

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CHECK_ONLY=false
for arg in "$@"; do
  [[ "$arg" == "--check" ]] && CHECK_ONLY=true
done

echo "=== Black (formatter) ==="
if $CHECK_ONLY; then
  black --check .
else
  black .
fi

echo ""
echo "=== Quality check complete ==="
