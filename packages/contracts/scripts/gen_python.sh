#!/usr/bin/env bash
# Regenerate Pydantic v2 models from packages/contracts/schemas into
# apps/core/aegis/contracts/generated/. Never hand-edit that directory.
set -euo pipefail
cd "$(dirname "$0")/../../.."

OUT="apps/core/aegis/contracts/generated"
rm -rf "$OUT"

.venv/bin/datamodel-codegen \
  --input packages/contracts/schemas \
  --input-file-type jsonschema \
  --output "$OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --use-schema-description \
  --disable-timestamp \
  --use-standard-collections \
  --use-union-operator \
  --formatters black isort

echo "wrote $OUT"
