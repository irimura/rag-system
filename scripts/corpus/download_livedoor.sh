#!/usr/bin/env bash
# 注意: livedoor ニュースコーパスは CC BY-ND 2.1 JP(改変禁止)です。
# 本スクリプトは原文を変更せず展開し、社内評価用途に限定します。成果物を再配布しないでください。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_command curl
require_command tar
ensure_dir "${RAW_DIR}/livedoor"

: "${LIVEDOOR_URL:=https://www.rondhuit.com/download/ldcc-20140209.tar.gz}"

echo "注意: livedoor ニュースコーパスは CC BY-ND 2.1 JP(改変禁止)・社内評価限定です。"
echo "本文を書き換えず、要約を保存せず、検索内部のチャンクを含む成果物を再配布しないでください。"

archive="${RAW_DIR}/livedoor/ldcc-20140209.tar.gz"
download_file "${LIVEDOOR_URL}" "${archive}"

if [[ -d "${RAW_DIR}/livedoor/text" ]] && [[ "$(file_count "${RAW_DIR}/livedoor/text" '*.txt')" -gt 0 ]]; then
  echo "展開済みのためスキップ: ${RAW_DIR}/livedoor/text"
else
  echo "展開開始: ${archive}"
  tar -xzf "${archive}" -C "${RAW_DIR}/livedoor"
  echo "展開完了: ${RAW_DIR}/livedoor/text"
fi

article_count="$(find "${RAW_DIR}/livedoor/text" -type f -name '*.txt' ! -name 'LICENSE.txt' -print | wc -l)"
license_count="$(find "${RAW_DIR}/livedoor/text" -type f -name 'LICENSE.txt' -print | wc -l)"
echo "livedoor 展開結果: 記事 ${article_count} 件 / LICENSE ${license_count} 件"
