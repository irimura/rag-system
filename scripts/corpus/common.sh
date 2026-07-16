#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/corpus.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "設定ファイルがありません: ${ENV_FILE}" >&2
  echo "先に cp -v ${SCRIPT_DIR}/corpus.env.example ${ENV_FILE} を実行してください。" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

: "${CORPUS_DIR:?corpus.env で CORPUS_DIR を設定してください}"

RAW_DIR="${CORPUS_DIR}/raw"
PROCESSED_DIR="${CORPUS_DIR}/processed"

require_command() {
  local command_name="${1}"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "必要なコマンドがありません: ${command_name}" >&2
    exit 1
  fi
}

ensure_dir() {
  local directory="${1}"
  if [[ ! -d "${directory}" ]]; then
    mkdir -v -p "${directory}"
  fi
}

file_count() {
  local directory="${1}"
  local pattern="${2:-*}"
  find "${directory}" -type f -name "${pattern}" -print | wc -l
}

download_file() {
  local url="${1}"
  local output="${2}"
  local partial="${output}.part"

  if [[ -s "${output}" ]]; then
    echo "取得済みのためスキップ: ${output}"
    return 0
  fi

  echo "取得開始: ${url}"
  curl --fail --location --retry 3 --continue-at - --output "${partial}" "${url}"
  if [[ ! -s "${partial}" ]]; then
    echo "取得結果が空です: ${url}" >&2
    exit 1
  fi
  mv -v "${partial}" "${output}"
  echo "取得完了: ${output} ($(stat -c '%s' "${output}") bytes)"
}
