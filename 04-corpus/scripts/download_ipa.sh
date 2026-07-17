#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_command curl
ensure_dir "${RAW_DIR}/ipa"

if [[ -z "${IPA_PDF_URLS:-}" ]]; then
  echo "IPA_PDF_URLS が未設定です。https://www.ipa.go.jp/security/reports/ から対象 PDF を確認してください。" >&2
  exit 2
fi

requested=0
for url in ${IPA_PDF_URLS}; do
  requested=$((requested + 1))
  filename="$(basename "${url%%\?*}")"
  if [[ "${filename}" != *.pdf ]]; then
    echo "PDF URL と判定できません: ${url}" >&2
    exit 1
  fi
  download_file "${url}" "${RAW_DIR}/ipa/${filename}"
done

cat > "${RAW_DIR}/ipa/SOURCE.md" <<EOF
# IPA 公開資料の出典

- 発行元: 独立行政法人情報処理推進機構(IPA)
- 配布ページ: ${IPA_SOURCE_PAGE_URLS:-https://www.ipa.go.jp/security/reports/}
- 取得 URL: ${IPA_PDF_URLS}
- 利用条件: 各資料の掲載ページに従い、IPA 名・資料名・URL を出典として明記する。
EOF

actual="$(file_count "${RAW_DIR}/ipa" '*.pdf')"
echo "IPA PDF: 指定 ${requested} 件 / 保存済み ${actual} 件"
