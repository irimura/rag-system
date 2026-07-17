#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_command curl
ensure_dir "${RAW_DIR}/whitepaper"

: "${WHITEPAPER_YEAR:?corpus.env で WHITEPAPER_YEAR を設定してください}"
: "${SOUMU_WHITEPAPER_FILENAME:=information-communications-whitepaper-${WHITEPAPER_YEAR}.pdf}"
: "${SOUMU_WHITEPAPER_PAGE_URL:=https://www.soumu.go.jp/johotsusintokei/whitepaper/}"

output="${RAW_DIR}/whitepaper/${SOUMU_WHITEPAPER_FILENAME}"
if [[ -s "${output}" ]]; then
  echo "取得済みのためスキップ: ${output}"
elif [[ -z "${SOUMU_WHITEPAPER_URL:-}" ]]; then
  echo "情報通信白書 ${WHITEPAPER_YEAR} 年度版の PDF URL が未設定です。" >&2
  echo "公式ページ ${SOUMU_WHITEPAPER_PAGE_URL} で対象年度の PDF を確認し、次のいずれかを実施してください。" >&2
  echo "1) corpus.env の SOUMU_WHITEPAPER_URL を設定して再実行する" >&2
  echo "2) ${output} へ手動配置して再実行する" >&2
  exit 2
else
  download_file "${SOUMU_WHITEPAPER_URL}" "${output}"
fi

cat > "${RAW_DIR}/whitepaper/SOURCE.md" <<EOF
# 情報通信白書の出典

- 発行元: 総務省
- 対象年度: ${WHITEPAPER_YEAR}
- 配布ページ: ${SOUMU_WHITEPAPER_PAGE_URL}
- PDF: ${SOUMU_WHITEPAPER_URL:-手動取得のため corpus.env では未設定}
- 利用条件: 政府標準利用規約(CC BY 4.0 互換)。利用時は出典を明記する。
EOF

echo "情報通信白書 PDF: $(file_count "${RAW_DIR}/whitepaper" '*.pdf') 件"
