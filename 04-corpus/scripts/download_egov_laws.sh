#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_command curl
ensure_dir "${RAW_DIR}/egov"

: "${EGOV_API_BASE:=https://laws.e-gov.go.jp/api/1/lawdata}"
: "${EGOV_LAW_IDS:?corpus.env で EGOV_LAW_IDS を設定してください}"

requested=0
for law_id in ${EGOV_LAW_IDS}; do
  requested=$((requested + 1))
  download_file "${EGOV_API_BASE}/${law_id}" "${RAW_DIR}/egov/${law_id}.xml"
done

actual="$(file_count "${RAW_DIR}/egov" '*.xml')"
echo "e-Gov 法令 XML: 指定 ${requested} 件 / 保存済み ${actual} 件"
