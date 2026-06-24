#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
chat_model="${OLLAMA_MODEL:-}"
embedding_model="${RAG_EMBEDDING_MODEL:-embeddinggemma}"
[[ -n "$chat_model" ]] || { echo "Állítsd be az OLLAMA_MODEL értékét a .env fájlban." >&2; exit 2; }
compose up -d ollama
installed="$(compose exec -T ollama ollama list | awk 'NR > 1 {print $1}')"
pull_if_missing() {
  local model="$1"
  if grep -Fxq "$model" <<<"$installed" || { [[ "$model" != *:* ]] && grep -Fxq "$model:latest" <<<"$installed"; }; then
    echo "Már telepítve: $model"
  else
    compose exec ollama ollama pull "$model"
  fi
}
pull_if_missing "$chat_model"
if [[ "${RAG_EMBEDDING_PROVIDER:-local_hash}" == ollama ]]; then pull_if_missing "$embedding_model"; fi
echo "Modellek telepítve. A dokumentumokat embeddingmodell-váltás után indexeld újra."
