#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_command curl
require_command grep
ensure_dir "${RAW_DIR}/wikipedia"

mode="${WIKIPEDIA_MODE:-partial}"
if [[ "${1:-}" == "--mode" ]]; then
  mode="${2:-}"
elif [[ -n "${1:-}" ]]; then
  mode="${1}"
fi

if [[ "${mode}" != "full" && "${mode}" != "partial" ]]; then
  echo "使い方: ${0} [--mode full|partial]" >&2
  exit 1
fi

: "${WIKIPEDIA_DUMP_DATE:=latest}"
base_url="https://dumps.wikimedia.org/jawiki/${WIKIPEDIA_DUMP_DATE}"

if [[ "${mode}" == "full" ]]; then
  filename="jawiki-${WIKIPEDIA_DUMP_DATE}-pages-articles.xml.bz2"
  url="${base_url}/${filename}"
else
  if [[ -n "${WIKIPEDIA_PARTIAL_URL:-}" ]]; then
    url="${WIKIPEDIA_PARTIAL_URL}"
    filename="$(basename "${url%%\?*}")"
  else
    echo "先頭分割ファイルを公式ディレクトリから検出します: ${base_url}/"
    filename="$(curl --fail --location "${base_url}/" | grep -oE "jawiki-${WIKIPEDIA_DUMP_DATE}-pages-articles-multistream1\.xml-p[0-9]+p[0-9]+\.bz2" | sort -u | sed -n '1p')"
    if [[ -z "${filename}" ]]; then
      echo "先頭分割ファイルを検出できません。corpus.env の WIKIPEDIA_PARTIAL_URL を設定してください。" >&2
      exit 2
    fi
    url="${base_url}/${filename}"
  fi
fi

download_file "${url}" "${RAW_DIR}/wikipedia/${filename}"

cat > "${RAW_DIR}/wikipedia/SOURCE.md" <<EOF
# Wikipedia 日本語版ダンプの出典

- 配布元: Wikimedia Downloads
- ダンプ日付: ${WIKIPEDIA_DUMP_DATE}
- モード: ${mode}
- URL: ${url}
- コンテンツライセンス: CC BY-SA 4.0。抽出後も記事名・元 URL・同ライセンスを保持する。
EOF

echo "Wikipedia ダンプ: $(file_count "${RAW_DIR}/wikipedia" '*.bz2') 件"
